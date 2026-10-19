from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import UniqueConstraint

course_teacher = db.Table(
    'course_teacher',
    db.Column('course_id', db.Integer, db.ForeignKey('course.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True),
)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    full_name = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    school_class = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    role = db.Column(db.String(20), default='student')
    # Для ученика: id аккаунта родителя (роль parent). Заполняется в админке.
    parent_guardian_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    parent_guardian = db.relationship(
        'User',
        remote_side=[id],
        foreign_keys=[parent_guardian_id],
        backref=db.backref('linked_students', lazy=True),
    )
    courses = db.relationship(
        'Course',
        secondary='user_course',
        backref=db.backref('users', lazy=True),
        lazy=True,
        overlaps='user_courses,user,course'
    )
    user_courses = db.relationship(
        'UserCourse',
        back_populates='user',
        cascade='all, delete-orphan',
        lazy=True,
        overlaps='courses,users'
    )
    homework_submissions = db.relationship('HomeworkSubmission', backref='user', lazy=True)
 
    test_results = db.relationship('TestResult', backref='user', lazy=True)
    login_events = db.relationship('LoginEvent', backref='user', lazy=True, cascade='all, delete-orphan')
    material_views = db.relationship('MaterialView', backref='user', lazy=True, cascade='all, delete-orphan')
    teaching_courses = db.relationship(
        'Course',
        secondary=course_teacher,
        backref=db.backref('assigned_teachers', lazy=True),
        lazy=True,
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    subject = db.Column(db.String(80), nullable=True)
    school_class = db.Column(db.String(20), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    author = db.relationship('User', backref=db.backref('authored_courses', lazy=True))

    tests = db.relationship('Test', backref='course', lazy=True)
    user_courses = db.relationship(
        'UserCourse',
        back_populates='course',
        cascade='all, delete-orphan',
        lazy=True,
        overlaps='courses,users'
    )
    materials = db.relationship(
        'CourseMaterial',
        back_populates='course',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='CourseMaterial.sort_order',
    )

    def __repr__(self):
        return f'<Course {self.title}>'



class CourseMaterial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    # Путь относительно папки static, например uploads/materials/foo.pdf; либо только external_url
    file_path = db.Column(db.String(512), nullable=True)
    external_url = db.Column(db.String(1024), nullable=True)
    # True: только записанные на курс студенты (+ автор/админ). False: любой авторизованный пользователь
    course_students_only = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    category = db.Column(db.String(32), nullable=False, default='theory')
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    course = db.relationship('Course', back_populates='materials')
    versions = db.relationship(
        'MaterialVersion',
        back_populates='material',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='MaterialVersion.version.desc()',
    )

    def __repr__(self):
        return f'<CourseMaterial {self.title}>'

# --- Новые модели для тестов ---
# Модель теста (например, "Тест по математике")
class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))  # Связь с курсом
    is_homework = db.Column(db.Boolean, default=False)
    # Связь с вопросами (один тест — много вопросов)
    questions = db.relationship(
        'Question',
        backref='test',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='Question.id',
    )
    test_results = db.relationship('TestResult', backref='test', lazy=True)
    homeworks = db.relationship('Homework', backref='test', lazy=True)

    def __repr__(self):
        return f'<Test {self.title}>'

# Модель вопроса (например, "Сколько будет 2+2?")
class Question(db.Model):
    # single_choice / multiple_choice / text_answer (эталон в Option) / file_upload
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'))  # Связь с тестом
    question_type = db.Column(db.String(20), nullable=False, default='single_choice')

    # Связь с вариантами ответов (один вопрос — много вариантов)
    options = db.relationship('Option', backref='question', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Question {self.text[:20]}...>'

# Модель варианта ответа (например, "4", "5", "6")
class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)  # Правильный ли вариант
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))  # Связь с вопросом

    def __repr__(self):
        return f'<Option {self.text}>' 

# Модель результата теста (что прошёл пользователь)
class TestResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Кто прошёл тест
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'))  # Какой тест
    score = db.Column(db.Integer)  # Количество правильных ответов (только автооценка: выбор из вариантов)
    total_questions = db.Column(db.Integer)  # Число вопросов с автооценкой
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)  # Когда прошёл тест
    file_submissions = db.relationship(
        'QuestionFileSubmission',
        backref='test_result',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<TestResult {self.user.username} - {self.test.title}: {self.score}/{self.total_questions}>'


# Ответ на вопрос типа «файл/скан» в рамках попытки теста (проверка учителем)
class QuestionFileSubmission(db.Model):
    __table_args__ = (
        UniqueConstraint('test_result_id', 'question_id', name='uq_test_result_question_file'),
    )
    id = db.Column(db.Integer, primary_key=True)
    test_result_id = db.Column(db.Integer, db.ForeignKey('test_result.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_reviewed = db.Column(db.Boolean, default=False)
    teacher_comment = db.Column(db.Text, nullable=True)

    question = db.relationship('Question', backref=db.backref('file_submissions', lazy=True))

    def __repr__(self):
        return f'<QuestionFileSubmission tr={self.test_result_id} q={self.question_id}>'
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Связующая таблица для записи пользователя на курс
class UserCourse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    progress = db.Column(db.Float, default=0.0)  # Прогресс в процентах (0-100)
    user = db.relationship(
        'User',
        back_populates='user_courses',
        overlaps='courses,users'
    )
    course = db.relationship(
        'Course',
        back_populates='user_courses',
        overlaps='courses,users'
    )
  
    def __repr__(self):
        return f'<UserCourse {self.id}>'  # Просто отображаем ID, чтобы избежать ошибок

# Домашнее задание
class Homework(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    course = db.relationship('Course', backref=db.backref('homeworks', lazy=True))
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'))  # Связь с тестом (если ДЗ — это тест)
    is_essay = db.Column(db.Boolean, default=False)  # Требует ли прикрепления файла
    deadline = db.Column(db.DateTime)  # Дедлайн

    # Связи
    submissions = db.relationship('HomeworkSubmission', backref='homework', lazy=True)

    def __repr__(self):
        return f'<Homework {self.title}>'

# Прикреплённые файлы к домашним заданиям
class HomeworkSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    homework_id = db.Column(db.Integer, db.ForeignKey('homework.id'))
    file_path = db.Column(db.String(256))  # Путь к файлу на сервере
    is_approved = db.Column(db.Boolean, default=False)  # Подтверждено ли учителем
    is_rejected = db.Column(db.Boolean, default=False)
    rejection_reason = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<HomeworkSubmission {self.user.username} - {self.homework.title}>'

# Расписание занятий
class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    course = db.relationship('Course', backref=db.backref('schedules', lazy=True))
    start_time = db.Column(db.DateTime, nullable=False)  # Время начала
    end_time = db.Column(db.DateTime, nullable=False)    # Время окончания
    topic = db.Column(db.String(200), nullable=False)    # Тема занятия
    week_number = db.Column(db.Integer, nullable=False)  # Номер недели

    def __repr__(self):
        return f'<Schedule {self.course.title} - {self.topic}>'


class Attendance(db.Model):
    """Посещаемость занятия из расписания."""
    __table_args__ = (
        UniqueConstraint('user_id', 'schedule_id', name='uq_attendance_user_schedule'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    schedule_id = db.Column(
        db.Integer, db.ForeignKey('schedule.id', ondelete='CASCADE'), nullable=False
    )
    # present | absent | late
    status = db.Column(db.String(20), nullable=False)

    user = db.relationship('User', backref=db.backref('attendance_records', lazy=True))
    schedule = db.relationship('Schedule', backref=db.backref('attendance_records', lazy=True))

    def __repr__(self):
        return f'<Attendance u={self.user_id} s={self.schedule_id} {self.status}>'


class MaterialVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('course_material.id', ondelete='CASCADE'), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    file_path = db.Column(db.String(512), nullable=True)
    external_url = db.Column(db.String(1024), nullable=True)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    material = db.relationship('CourseMaterial', back_populates='versions')
    created_by = db.relationship('User', foreign_keys=[created_by_id])


class LoginEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)


class MaterialView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('course_material.id', ondelete='CASCADE'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    material = db.relationship('CourseMaterial', backref=db.backref('views', lazy=True))


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    author = db.relationship('User', backref=db.backref('announcements', lazy=True))

    def __repr__(self):
        return f'<Announcement {self.title[:30]}>'