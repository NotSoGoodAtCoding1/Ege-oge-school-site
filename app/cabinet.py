"""Role-based personal cabinet destinations."""
from app.security import is_admin_user


def cabinet_endpoint_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return "login"
    if is_admin_user(user):
        return "admin_dashboard"
    if user.role == "teacher":
        return "teacher_dashboard"
    if user.role == "parent":
        return "parent_dashboard"
    return "profile"
