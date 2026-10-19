"""Shared security helpers for routes and admin modules."""
import os
from urllib.parse import urlparse

from flask_login import current_user

# Document and image types allowed for homework / test file answers.
ALLOWED_SUBMISSION_EXTENSIONS = frozenset({
    '.pdf', '.doc', '.docx', '.odt', '.png', '.jpg', '.jpeg', '.gif', '.webp',
    '.txt', '.rtf', '.heic',
})

RESERVED_USERNAMES = frozenset({
    'admin', 'administrator', 'root', 'system', 'support', 'moderator',
})

ALLOWED_USER_ROLES = frozenset({'student', 'teacher', 'parent', 'admin'})


def is_admin_user(user=None):
    user = user or current_user
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'role', None) == 'admin'
    )


def is_reserved_username(username):
    if not username:
        return False
    return username.strip().lower() in RESERVED_USERNAMES


def normalize_role(role, default='student'):
    value = (role or default).strip().lower()
    return value if value in ALLOWED_USER_ROLES else default


def is_safe_external_url(url):
    """Allow only http(s) links (blocks javascript:, data:, etc.)."""
    if not url or not str(url).strip():
        return False
    try:
        parsed = urlparse(str(url).strip())
    except ValueError:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    if not parsed.netloc:
        return False
    host = parsed.netloc.lower().split('@')[-1]
    if host in ('localhost', '127.0.0.1', '0.0.0.0'):
        return False
    return True


def submission_extension(filename):
    if not filename:
        return None
    ext = os.path.splitext(filename.replace('\\', '/').split('/')[-1])[1].lower()
    return ext if ext in ALLOWED_SUBMISSION_EXTENSIONS else None


def upload_abs_path(stored_path):
    """Resolve a DB-stored path to an absolute filesystem path under the app."""
    if not stored_path:
        return None
    norm = stored_path.replace('\\', '/').lstrip('/')
    if norm.startswith('app/static/'):
        rel = norm[len('app/static/'):]
    elif norm.startswith('static/'):
        rel = norm[len('static/'):]
    else:
        rel = norm
    from flask import current_app
    return os.path.join(current_app.static_folder, rel)


def can_access_homework_submission(submission, user):
    if not submission or not user or not user.is_authenticated:
        return False
    hw = submission.homework
    course = hw.course if hw else None
    if submission.user_id == user.id:
        return True
    if is_admin_user(user):
        return True
    if user.role == 'teacher' and course and course.author_id == user.id:
        return True
    if user.role == 'parent':
        student = submission.user
        return student and student.parent_guardian_id == user.id
    return False


def can_access_course_material(material, user):
    if not material or not user or not user.is_authenticated:
        return False
    course = material.course
    if not course:
        return False
    if is_admin_user(user):
        return True
    if user.role == 'teacher' and course.author_id == user.id:
        return True
    if not material.course_students_only:
        return True
    from app.models import UserCourse
    return UserCourse.query.filter_by(
        user_id=user.id, course_id=course.id,
    ).first() is not None


def can_access_test_file_submission(submission, user):
    if not submission or not user or not user.is_authenticated:
        return False
    tr = submission.test_result
    if not tr:
        return False
    test = tr.test
    course = test.course if test else None
    if tr.user_id == user.id:
        return True
    if is_admin_user(user):
        return True
    if user.role == 'teacher' and course and course.author_id == user.id:
        return True
    if user.role == 'parent':
        student = tr.user
        return student and student.parent_guardian_id == user.id
    return False
