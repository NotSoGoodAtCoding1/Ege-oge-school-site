from app.manage_routes_users import register_user_routes
from app.manage_routes_courses import register_course_routes
from app.manage_routes_reports import register_report_routes

def init_manage_routes(app):
    register_user_routes(app)
    register_course_routes(app)
    register_report_routes(app)
