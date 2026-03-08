def require_role(user, allowed_roles: list):
    if user["role"] not in allowed_roles:
        raise Exception("Permission denied")
