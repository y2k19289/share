import os
import json
import base64
import logging
import hashlib
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

try:
    from kubernetes import client as k8s_client, config as k8s_config
    K8S_AVAILABLE = True
except Exception:
    K8S_AVAILABLE = False

LOG = logging.getLogger("update_eks_secrets")
LOG.setLevel(logging.INFO)

SECRETS_CLIENT = boto3.client("secretsmanager")

MAPPINGS_FILE = os.environ.get("MAPPINGS_FILE", "/var/task/mappings.json")
KUBECONFIG = os.environ.get("KUBECONFIG")


def load_mappings() -> Dict[str, Any]:
    with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_secret_value(secret_id: str) -> Dict[str, Any]:
    try:
        resp = SECRETS_CLIENT.get_secret_value(SecretId=secret_id)
    except ClientError as e:
        LOG.exception("Failed to get secret %s: %s", secret_id, e)
        raise

    if "SecretString" in resp:
        return json.loads(resp["SecretString"]) if _is_json(resp["SecretString"]) else {"value": resp["SecretString"]}
    elif "SecretBinary" in resp:
        data = base64.b64decode(resp["SecretBinary"])
        return json.loads(data)
    return {}


def _is_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


def set_nested(d: Dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def get_nested(d: Dict[str, Any], path: str, default=None):
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def delete_nested(d: Dict[str, Any], path: str) -> None:
    parts = path.split(".")
    cur = d
    chain = []
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return
        chain.append((cur, p))
        cur = cur[p]

    if not isinstance(cur, dict) or parts[-1] not in cur:
        return

    del cur[parts[-1]]

    # Remove empty parent objects left behind after deleting the nested leaf.
    for parent, key in reversed(chain):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]
        else:
            break


def _build_secret_token(secret_string: str) -> str:
    # Deterministic token makes repeated writes with identical payload idempotent.
    return hashlib.sha256(secret_string.encode("utf-8")).hexdigest()


def update_secretsmanager_target(target_secret_name: str, key_path: str, new_password: str):
    try:
        resp = SECRETS_CLIENT.get_secret_value(SecretId=target_secret_name)
    except ClientError:
        LOG.exception("Target secret %s not found", target_secret_name)
        raise

    if "SecretString" in resp:
        secret_str = resp["SecretString"]
        if not _is_json(secret_str):
            raise ValueError(
                f"Target secret {target_secret_name} must be a JSON object when target_secret_key_path is configured"
            )
        secret_obj = json.loads(secret_str)
    else:
        raise ValueError(
            f"Target secret {target_secret_name} must store a JSON object when target_secret_key_path is configured"
        )

    if key_path in {"", None}:
        current_value = secret_obj.get("value") if isinstance(secret_obj, dict) else None
        if current_value == new_password:
            LOG.info("Secret %s already has desired plaintext value; skipping write", target_secret_name)
            return

        secret_obj = {"value": new_password}
        payload = json.dumps(secret_obj, separators=(",", ":"), sort_keys=True)
        token = _build_secret_token(payload)
        try:
            SECRETS_CLIENT.put_secret_value(
                SecretId=target_secret_name,
                SecretString=payload,
                ClientRequestToken=token,
            )
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "LimitExceededException":
                latest = get_secret_value(target_secret_name)
                latest_value = latest.get("value") if isinstance(latest, dict) else None
                if latest_value == new_password:
                    LOG.info("Secret %s already updated by another invocation", target_secret_name)
                    return
            raise
        LOG.info("Updated secret %s with plaintext value", target_secret_name)
        return

    if not isinstance(secret_obj, dict):
        secret_obj = {}

    # Prefer a direct key update (including dotted keys) so the secret stays
    # compatible with Secrets Manager key/value mode.
    if secret_obj.get(key_path) == new_password:
        LOG.info("Secret %s key %s already has desired value; skipping write", target_secret_name, key_path)
        return

    secret_obj[key_path] = new_password

    # Cleanup from older behavior that created nested objects for dotted keys.
    if "." in key_path:
        delete_nested(secret_obj, key_path)

    payload = json.dumps(secret_obj, separators=(",", ":"), sort_keys=True)
    token = _build_secret_token(payload)
    try:
        SECRETS_CLIENT.put_secret_value(
            SecretId=target_secret_name,
            SecretString=payload,
            ClientRequestToken=token,
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "LimitExceededException":
            latest = get_secret_value(target_secret_name)
            if isinstance(latest, dict) and latest.get(key_path) == new_password:
                LOG.info("Secret %s key %s already updated by another invocation", target_secret_name, key_path)
                return
        raise
    LOG.info("Updated secret %s key %s", target_secret_name, key_path)


def init_k8s_client():
    if not K8S_AVAILABLE:
        raise RuntimeError("kubernetes package not available")


def update_k8s_secret(namespace: str, secret_name: str, secret_key: str, new_password: str):
    if not K8S_AVAILABLE:
        LOG.warning("Kubernetes client not available; skipping k8s secret update")
        return
    init_k8s_client()
    v1 = k8s_client.CoreV1Api()
    try:
        secret = v1.read_namespaced_secret(secret_name, namespace)
    except Exception:
        LOG.exception("Failed to read k8s secret %s/%s", namespace, secret_name)
        raise

    data = secret.data or {}
    import base64 as _b64
    data[secret_key] = _b64.b64encode(new_password.encode()).decode()
    body = {"data": data}
    v1.patch_namespaced_secret(secret_name, namespace, body)
    LOG.info("Patched k8s secret %s/%s key %s", namespace, secret_name, secret_key)


def restart_pods(namespace: str, label_selector: str):
    if not K8S_AVAILABLE:
        LOG.warning("Kubernetes client not available; skipping pod restart")
        return
    init_k8s_client()
    v1 = k8s_client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
    for p in pods.items:
        try:
            v1.delete_namespaced_pod(p.metadata.name, namespace)
            LOG.info("Deleted pod %s/%s to trigger restart", namespace, p.metadata.name)
        except Exception:
            LOG.exception("Failed to delete pod %s/%s", namespace, p.metadata.name)


def find_mapping_for_rds_secret(secret_id: str, mappings: Dict[str, Any]):
    for m in mappings.get("mappings", []):
        source_name = m.get("rds_secret_name")
        if source_name and (source_name == secret_id or source_name in secret_id):
            return m
    return None


def extract_password_from_secret(secret_obj: Any) -> str:
    if isinstance(secret_obj, str):
        return secret_obj

    if isinstance(secret_obj, dict):
        for k in ("password", "Password", "dbPassword", "value"):
            value = secret_obj.get(k)
            if isinstance(value, str) and value:
                return value

        for value in secret_obj.values():
            if isinstance(value, dict):
                try:
                    return extract_password_from_secret(value)
                except ValueError:
                    continue
            if isinstance(value, str) and value:
                return value

    raise ValueError("Could not extract password from secret object")


def lambda_handler(event, context):
    LOG.info("Received event: %s", json.dumps(event))

    secret_id = None
    if isinstance(event, dict):
        secret_id = event.get("SecretId") or event.get("secretId")
        detail = event.get("detail") or {}
        if not secret_id:
            secret_id = detail.get("SecretId") or detail.get("requestParameters", {}).get("secretId")

    if not secret_id:
        raise ValueError("SecretId not found in event")

    mappings = load_mappings()
    mapping = find_mapping_for_rds_secret(secret_id, mappings)
    if not mapping:
        LOG.info("No mapping configured for %s; nothing to do", secret_id)
        return {"status": "no_mapping"}

    secret_obj = get_secret_value(secret_id)
    new_password = extract_password_from_secret(secret_obj)

    if mapping.get("target_secretsmanager_secret") and mapping.get("target_secret_key_path"):
        update_secretsmanager_target(mapping["target_secretsmanager_secret"], mapping["target_secret_key_path"], new_password)

    if mapping.get("k8s"):
        k = mapping["k8s"]
        ns = k.get("namespace")
        name = k.get("secret_name")
        key = k.get("secret_key")
        update_k8s_secret(ns, name, key, new_password)

        restart_selector = k.get("restart_label_selector")
        if restart_selector:
            restart_pods(ns, restart_selector)

    return {"status": "updated", "secret": secret_id}
