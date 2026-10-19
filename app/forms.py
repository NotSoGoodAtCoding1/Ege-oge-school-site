from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, BooleanField, SubmitField, TextAreaField,
    SelectField, FieldList, FormField, SelectMultipleField, FileField,
)
from wtforms.form import Form as WTForm
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError


def _safe_url_validator(form, field):
    from app.security import is_safe_external_url
    value = (field.data or '').strip()
    if value and not is_safe_external_url(value):
        raise ValidationError('Ссылка должна начинаться с http:// или https://')

# --- Существующие формы ---
class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Повторите пароль', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')


class AnnouncementForm(FlaskForm):
    title = StringField('Заголовок', validators=[DataRequired(), Length(max=200)])
    body = TextAreaField('Текст объявления', validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField('Опубликовать')

# --- Новые формы ---
# Форма для создания теста
class TestForm(FlaskForm):
    title = StringField('Название теста', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Описание теста')
    course_id = SelectField('Курс', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Создать тест')

class OptionEntryForm(WTForm):
    class Meta:
        csrf = False

    text = StringField('Текст варианта', validators=[Optional(), Length(max=200)])
    is_correct = BooleanField('Верный')


class QuestionBuilderForm(FlaskForm):
    text = TextAreaField('Текст вопроса', validators=[DataRequired()])
    question_type = SelectField(
        'Тип вопроса',
        coerce=str,
        choices=[
            ('single_choice', 'Один верный ответ'),
            ('multiple_choice', 'Несколько верных ответов'),
            ('text_answer', 'Текстовый ответ (задаётся учителем)'),
            ('file_upload', 'Ответ сканом или файлом (проверка учителем)'),
        ],
        validators=[DataRequired()],
    )
    correct_answer = StringField(
        'Верный ответ',
        validators=[Optional(), Length(max=500)],
        description='Для текстового вопроса — эталон для автопроверки.',
    )
    options = FieldList(FormField(OptionEntryForm), min_entries=2, max_entries=50)
    submit = SubmitField('Добавить вопрос')


class CourseForm(FlaskForm):
    title = StringField('Название курса', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Описание')
    submit = SubmitField('Сохранить')


class CourseMaterialForm(FlaskForm):
    title = StringField('Название', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Краткое описание (необязательно)')
    external_url = StringField(
        'Ссылка (YouTube, сайт…)',
        validators=[Optional(), Length(max=1024), _safe_url_validator],
    )
    course_students_only = BooleanField(
        'Только для студентов, записанных на этот курс',
        default=True,
    )
    submit = SubmitField('Добавить материал')


class HomeworkManageForm(FlaskForm):
    title = StringField('Название', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Описание')
    test_id = SelectField('Связанный тест', coerce=int)
    is_essay = BooleanField('Требуется загрузка файла', default=False)
    deadline = StringField('Дедлайн (необязательно, формат ГГГГ-ММ-ДДTчч:мм)', validators=[Optional()])
    submit = SubmitField('Создать задание')


class ScheduleLessonForm(FlaskForm):
    start_time = StringField('Начало (ГГГГ-ММ-ДДTчч:мм)', validators=[DataRequired()])
    end_time = StringField('Окончание (ГГГГ-ММ-ДДTчч:мм)', validators=[DataRequired()])
    topic = StringField('Тема', validators=[DataRequired(), Length(max=200)])
    week_number = StringField('Номер недели', validators=[DataRequired()])
    submit = SubmitField('Добавить в расписание')


class FileReviewForm(FlaskForm):
    teacher_comment = TextAreaField('Комментарий для студента', validators=[Optional()])
    submit = SubmitField('Отметить как проверенное')


class HomeworkRejectForm(FlaskForm):
    rejection_reason = TextAreaField(
        'Причина отклонения (будет видна студенту)',
        validators=[DataRequired(), Length(max=2000)],
    )
    submit = SubmitField('Отклонить')


ROLE_CHOICES = [
    ('student', 'Ученик'),
    ('teacher', 'Учитель'),
    ('parent', 'Родитель'),
    ('admin', 'Администратор'),
]

CLASS_CHOICES = [
    ('', '— не указан —'),
    ('9', '9 класс'),
    ('10', '10 класс'),
    ('11', '11 класс'),
]

SUBJECT_CHOICES = [
    ('', '— не указан —'),
    ('math', 'Математика'),
    ('russian', 'Русский язык'),
    ('physics', 'Физика'),
    ('informatics', 'Информатика'),
    ('english', 'Английский'),
    ('chinese', 'Китайский'),
    ('other', 'Другое'),
]

MATERIAL_CATEGORY_CHOICES = [
    ('theory', 'Теория'),
    ('practice', 'Практика'),
    ('tests', 'Тесты'),
    ('homework', 'Домашние задания'),
]


class AdminUserForm(FlaskForm):
    username = StringField('Логин', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('ФИО', validators=[Optional(), Length(max=200)])
    phone = StringField('Телефон', validators=[Optional(), Length(max=32)])
    school_class = SelectField('Класс', choices=CLASS_CHOICES, validators=[Optional()])
    role = SelectField('Роль', choices=ROLE_CHOICES, validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[Optional(), Length(min=6)])
    password2 = PasswordField('Повторите пароль', validators=[Optional(), EqualTo('password')])
    course_ids = SelectMultipleField('Курсы', coerce=int, validators=[Optional()])
    teacher_course_ids = SelectMultipleField('Преподавание (курсы)', coerce=int, validators=[Optional()])
    parent_guardian_id = SelectField('Родитель (для ученика)', coerce=int, validators=[Optional()])
    is_active = BooleanField('Активен', default=True)
    submit = SubmitField('Сохранить')


class AdminBulkImportForm(FlaskForm):
    file = FileField('Файл CSV или Excel (.xlsx)', validators=[DataRequired()])
    default_password = StringField('Пароль по умолчанию для новых пользователей', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Импортировать')


class AdminCourseForm(FlaskForm):
    title = StringField('Название курса', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Описание')
    subject = SelectField('Предмет', choices=SUBJECT_CHOICES, validators=[Optional()])
    school_class = SelectField('Класс', choices=CLASS_CHOICES, validators=[Optional()])
    author_id = SelectField('Основной учитель', coerce=int, validators=[DataRequired()])
    teacher_ids = SelectMultipleField('Доп. учителя', coerce=int, validators=[Optional()])
    submit = SubmitField('Сохранить')


class AdminReportFilterForm(FlaskForm):
    report_type = SelectField(
        'Тип отчёта',
        choices=[
            ('activity', 'Активность'),
            ('grades', 'Оценки / тесты'),
            ('attendance', 'Посещаемость'),
        ],
        validators=[DataRequired()],
    )
    school_class = SelectField('Класс', choices=CLASS_CHOICES, validators=[Optional()])
    course_id = SelectField('Курс', coerce=int, validators=[Optional()])
    teacher_id = SelectField('Учитель', coerce=int, validators=[Optional()])
    date_from = StringField('С даты (ГГГГ-ММ-ДД)', validators=[Optional()])
    date_to = StringField('По дату (ГГГГ-ММ-ДД)', validators=[Optional()])
    submit = SubmitField('Скачать CSV')