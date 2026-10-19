from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from flask import abort
from config import Config
from app.security import is_admin_user, is_safe_external_url

# Инициализируем расширения БЕЗ привязки к приложению
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
admin = Admin(name='Админка школы ЕГЭ/ОГЭ')

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if app.config.get('SECRET_KEY') == 'dev-insecure-change-me-in-env':
        app.logger.warning(
            'SECRET_KEY is not set in the environment; sessions are not safe for production.'
        )

    # Инициализируем расширения с приложением
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    admin.init_app(app)

    # Настройки для Flask-Login
    login_manager.login_view = 'login'

    # Импортируем модели ПОСЛЕ инициализации db
    from app.models import (
        User, Course, CourseMaterial, Test, Question, Option, TestResult, QuestionFileSubmission,
        UserCourse, Homework, HomeworkSubmission, Schedule, Attendance,
    )

    # Кастомный ModelView с проверкой прав
    class AdminModelView(ModelView):
        def is_accessible(self):
            return is_admin_user(current_user)
        def inaccessible_callback(self, name, **kwargs):
            return abort(403)

    # Настраиваем отображение моделей в админке
    class UserAdmin(AdminModelView):
        column_exclude_list = ['password_hash']
        form_excluded_columns = ['password_hash']
        column_list = ['id', 'username', 'email', 'role', 'parent_guardian_id', 'courses']

        # Настраиваем отображение связи с курсами
        form_args = {
            'courses': {
                'label': 'Курсы',
                'query_factory': lambda: Course.query.all()  # Показываем все курсы для выбора
            }
        }

    class CourseAdmin(AdminModelView):
        column_list = ['id', 'title', 'description', 'author']
        column_labels = {'author': 'Автор', 'title': 'Название', 'description': 'Описание'}

    class CourseMaterialAdmin(AdminModelView):
        column_list = ['id', 'title', 'course', 'course_students_only', 'external_url', 'file_path']
        column_labels = {
            'title': 'Название',
            'course': 'Курс',
            'course_students_only': 'Только курс',
            'external_url': 'Ссылка',
            'file_path': 'Файл',
        }

    class TestAdmin(AdminModelView):
        column_list = ['id', 'title', 'description', 'course']
        column_labels = {'course': 'Курс', 'title': 'Название', 'description': 'Описание'}

    class QuestionAdmin(AdminModelView):
        column_list = ['id', 'text', 'question_type', 'test']
        column_labels = {
            'text': 'Текст вопроса',
            'question_type': 'Тип',
            'test': 'Тест',
        }

    class OptionAdmin(AdminModelView):
        column_list = ['id', 'text', 'is_correct', 'question']
        column_labels = {'text': 'Текст варианта', 'is_correct': 'Правильный?', 'question': 'Вопрос'}

    class TestResultAdmin(AdminModelView):
        column_list = ['id', 'user', 'test', 'score', 'total_questions', 'completed_at']
        column_labels = {
            'user': 'Пользователь',
            'test': 'Тест',
            'score': 'Баллы',
            'total_questions': 'Всего вопросов',
            'completed_at': 'Дата прохождения'
        }

    class QuestionFileSubmissionAdmin(AdminModelView):
        column_list = [
            'id', 'test_result', 'question', 'file_path',
            'submitted_at', 'is_reviewed', 'reviewed_at',
        ]
        column_labels = {
            'test_result': 'Попытка',
            'question': 'Вопрос',
            'file_path': 'Файл',
            'submitted_at': 'Загружено',
            'is_reviewed': 'Проверено',
            'reviewed_at': 'Дата проверки',
        }

            # Добавляем вьюхи для новых моделей
    class UserCourseAdmin(AdminModelView):
        column_list = ['id', 'user', 'course', 'progress']
        column_labels = {
            'user': 'Пользователь',
            'course': 'Курс',
            'progress': 'Прогресс (%)'
        }

    class ScheduleAdmin(AdminModelView):
        column_list = ['id', 'course', 'start_time', 'end_time', 'topic', 'week_number']
        column_labels = {
            'course': 'Курс',
            'start_time': 'Время начала',
            'end_time': 'Время окончания',
            'topic': 'Тема',
            'week_number': 'Номер недели'
        }
    
    class HomeworkAdmin(AdminModelView):
        column_list = ['id', 'title', 'course', 'test', 'is_essay', 'deadline']
        column_labels = {
            'title': 'Название',
            'course': 'Курс',
            'test': 'Тест',
            'is_essay': 'Требует файла?',
            'deadline': 'Дедлайн'
        }

    class HomeworkSubmissionAdmin(AdminModelView):
        column_list = ['id', 'user', 'homework', 'file_path', 'is_approved', 'is_rejected', 'rejection_reason']
        column_labels = {
            'user': 'Пользователь',
            'homework': 'Домашнее задание',
            'file_path': 'Путь к файлу',
            'is_approved': 'Проверено?',
            'is_rejected': 'Отклонено?',
            'rejection_reason': 'Причина отклонения',
        }

    class AttendanceAdmin(AdminModelView):
        column_list = ['id', 'user', 'schedule', 'status']
        column_labels = {
            'user': 'Ученик',
            'schedule': 'Занятие',
            'status': 'Статус',
        }

    # Добавляем модели в админку
    admin.add_view(UserAdmin(User, db.session, name='Пользователи'))
    admin.add_view(CourseAdmin(Course, db.session, name='Курсы'))
    admin.add_view(CourseMaterialAdmin(CourseMaterial, db.session, name='Материалы курсов'))
    admin.add_view(TestAdmin(Test, db.session, name='Тесты'))
    admin.add_view(QuestionAdmin(Question, db.session, name='Вопросы'))
    admin.add_view(OptionAdmin(Option, db.session, name='Варианты ответов'))
    admin.add_view(TestResultAdmin(TestResult, db.session, name='Результаты тестов'))
    admin.add_view(QuestionFileSubmissionAdmin(QuestionFileSubmission, db.session, name='Файлы ответов в тестах'))
     # Регистрируем новые вьюхи в админке
    admin.add_view(UserCourseAdmin(UserCourse, db.session, name='Записи на курсы'))
    admin.add_view(ScheduleAdmin(Schedule, db.session, name='Расписание'))
    admin.add_view(HomeworkAdmin(Homework, db.session, name='Домашние задания'))  # Добавляем Homework
    admin.add_view(HomeworkSubmissionAdmin(HomeworkSubmission, db.session, name='Сданные ДЗ'))
    admin.add_view(AttendanceAdmin(Attendance, db.session, name='Посещаемость'))

    # Импортируем маршруты и регистрируем их
    from app.routes import init_routes
    init_routes(app)

    from app.manage_routes import init_manage_routes
    init_manage_routes(app)

    from flask import url_for
    from flask_login import current_user
    from app.cabinet import cabinet_endpoint_for_user

    @app.context_processor
    def inject_cabinet_nav():
        def cabinet_url():
            return url_for(cabinet_endpoint_for_user(current_user))

        def show_student_tests_nav():
            return (
                current_user.is_authenticated
                and current_user.role == 'student'
            )

        return dict(cabinet_url=cabinet_url, show_student_tests_nav=show_student_tests_nav)

    @app.template_filter('safe_http_url')
    def safe_http_url_filter(url):
        return url if is_safe_external_url(url) else ''

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        print("База данных инициализирована.")

    @app.cli.command("upgrade-schema")
    def upgrade_schema():
        from app.schema_upgrade import upgrade_admin_schema
        db.create_all()
        upgrade_admin_schema(db)
        print("Схема обновлена (новые таблицы и колонки).")

    return app