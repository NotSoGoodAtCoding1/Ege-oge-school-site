import secrets
from datetime import datetime, timedelta

from flask import (
    render_template, redirect, url_for, flash, request, abort,
    send_from_directory, current_app,
)
from sqlalchemy import func, nullslast
from sqlalchemy.orm import joinedload
from flask_login import login_user, logout_user, current_user, login_required
from app.models import (
    User, Course, Test, Question, Option, TestResult, QuestionFileSubmission,
    UserCourse, Homework, HomeworkSubmission, Schedule, CourseMaterial, Attendance,
    LoginEvent, MaterialView, MaterialVersion, Announcement,
)
from app.forms import (
    LoginForm, RegistrationForm, AnnouncementForm,
    TestForm, QuestionBuilderForm,
    CourseForm, CourseMaterialForm, HomeworkManageForm, ScheduleLessonForm, FileReviewForm,
    HomeworkRejectForm,
)
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError
from app import db  # db инициализирован в __init__.py
from app.teachers_public import PUBLIC_TEACHERS, public_teachers_list
from app.security import (
    is_safe_external_url,
    submission_extension,
    upload_abs_path,
    can_access_homework_submission,
    can_access_test_file_submission,
    can_access_course_material,
    is_reserved_username,
    is_admin_user,
)
import os

ALLOWED_MATERIAL_EXTENSIONS = frozenset({
    '.pdf', '.doc', '.docx', '.odt', '.ods', '.xls', '.xlsx',
    '.txt', '.rtf', '.csv', '.ppt', '.pptx',
})

MATERIAL_EXTENSION_LABELS = {
    '.pdf': 'PDF',
    '.doc': 'Word',
    '.docx': 'Word',
    '.odt': 'Текст (ODT)',
    '.ods': 'Таблица (ODS)',
    '.xls': 'Excel',
    '.xlsx': 'Excel',
    '.txt': 'Текст',
    '.rtf': 'RTF',
    '.csv': 'CSV',
    '.ppt': 'PowerPoint',
    '.pptx': 'PowerPoint',
}


def material_extension_from_filename(filename):
    if not filename:
        return None
    ext = os.path.splitext(filename.replace('\\', '/').split('/')[-1])[1].lower()
    return ext if ext in ALLOWED_MATERIAL_EXTENSIONS else None


def safe_material_storage_name(original_filename):
    """ASCII-safe stored name; keeps extension from the original upload name."""
    ext = material_extension_from_filename(original_filename)
    if not ext:
        return None
    base = os.path.splitext(original_filename.replace('\\', '/').split('/')[-1])[0]
    safe_base = secure_filename(base) or 'file'
    return f'{safe_base}{ext}'


def material_file_label(file_path):
    if not file_path:
        return 'Файл'
    ext = os.path.splitext(file_path)[1].lower()
    return MATERIAL_EXTENSION_LABELS.get(ext, ext.lstrip('.').upper() or 'Файл')


def init_routes(app):
    def can_manage_tests(user):
        return bool(user and user.is_authenticated and user.role in ('teacher', 'admin'))

    def ensure_test_management_access():
        if not can_manage_tests(current_user):
            flash('Только преподаватели и администраторы могут создавать и редактировать тесты.', 'danger')
            return redirect(url_for('tests'))
        return None

    def ensure_teacher_or_admin():
        if not current_user.is_authenticated or current_user.role not in ('teacher', 'admin'):
            flash('Раздел доступен только преподавателям и администраторам.', 'danger')
            return redirect(url_for('index'))
        return None

    def teacher_manages_course(course):
        if not course:
            return False
        if current_user.role == 'admin':
            return True
        return current_user.role == 'teacher' and course.author_id == current_user.id

    def teacher_courses_query():
        if current_user.role == 'admin':
            return Course.query.order_by(Course.title)
        return Course.query.filter_by(author_id=current_user.id).order_by(Course.title)

    def parse_iso_datetime(value):
        if not value or not str(value).strip():
            return None
        try:
            return datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None

    def static_file_relative(path):
        if not path:
            return None
        norm = path.replace('\\', '/')
        if 'static/' in norm:
            return norm.split('static/', 1)[1]
        return norm

    def student_enrolled(course_id):
        return UserCourse.query.filter_by(
            user_id=current_user.id, course_id=course_id
        ).first() is not None

    def user_can_access_course(course):
        if not course:
            return False
        if is_admin_user(current_user):
            return True
        if teacher_manages_course(course):
            return True
        return student_enrolled(course.id)

    def user_can_take_test(test):
        if not test:
            return False
        if is_admin_user(current_user) or can_manage_tests(current_user):
            return True
        if not test.course_id:
            return True
        course = test.course or Course.query.get(test.course_id)
        return user_can_access_course(course)

    def save_submission_file(upload, prefix):
        ext = submission_extension(upload.filename)
        if not ext:
            return None, None
        token = secrets.token_hex(16)
        filename = f'{prefix}{token}{ext}'
        upload_dir = os.path.join('app', 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        rel_path = os.path.join(upload_dir, filename)
        upload.save(rel_path)
        return rel_path, filename

    def ensure_parent():
        if not current_user.is_authenticated or current_user.role != 'parent':
            flash('Раздел доступен только родителям.', 'danger')
            return redirect(url_for('index'))
        return None

    def homework_done_for_user(user_id, course_id, hw):
        if hw.is_essay:
            sub = HomeworkSubmission.query.filter_by(user_id=user_id, homework_id=hw.id).first()
            return bool(sub and sub.is_approved)
        if hw.test_id:
            return TestResult.query.filter_by(user_id=user_id, test_id=hw.test_id).first() is not None
        return False

    def progress_percent_for_course(user_id, course):
        total_tests = Test.query.filter_by(course_id=course.id).count()
        course_tests = Test.query.filter_by(course_id=course.id).all()
        test_ids = [t.id for t in course_tests]
        completed_tests = (
            TestResult.query.filter(
                TestResult.user_id == user_id,
                TestResult.test_id.in_(test_ids),
            ).count()
            if test_ids
            else 0
        )
        total_homeworks = Homework.query.filter_by(course_id=course.id).count()
        completed_homeworks = TestResult.query.join(Test).join(
            Homework, Homework.test_id == Test.id
        ).filter(
            Test.is_homework.is_(True),
            Homework.is_essay.is_(False),
            TestResult.user_id == user_id,
            Test.course_id == course.id,
        ).count()
        essay_hw_ids = [h.id for h in Homework.query.filter_by(course_id=course.id, is_essay=True).all()]
        completed_homeworks += HomeworkSubmission.query.filter(
            HomeworkSubmission.user_id == user_id,
            HomeworkSubmission.homework_id.in_(essay_hw_ids),
            HomeworkSubmission.is_approved.is_(True),
        ).count()
        total = total_tests + total_homeworks
        return (completed_tests + completed_homeworks) / total * 100 if total > 0 else 0.0

    def _parse_choice_option_rows(qform):
        rows = []
        for entry in qform.options.entries:
            data = entry.form.data
            text = (data.get('text') or '').strip()
            if text:
                rows.append((text, bool(data.get('is_correct'))))
        return rows

    def _normalize_text_answer(value):
        return (value or '').strip().casefold()

    def _validate_question_builder(qform):
        qtype = qform.question_type.data
        rows = _parse_choice_option_rows(qform)
        if qtype == 'file_upload':
            return True, None, []
        if qtype == 'text_answer':
            answer = (qform.correct_answer.data or '').strip()
            if not answer:
                return False, 'Укажите верный текстовый ответ для автопроверки.', None
            if len(answer) > 500:
                return False, 'Верный ответ не длиннее 500 символов.', None
            return True, None, [(answer, True)]
        if len(rows) < 2:
            return False, 'Для вопроса с вариантами ответа нужно минимум два непустых варианта.', None
        correct_n = sum(1 for _, ok in rows if ok)
        if correct_n < 1:
            return False, 'Отметьте хотя бы один верный вариант.', None
        if qtype == 'single_choice' and correct_n != 1:
            return False, 'Для типа «один верный ответ» отметьте ровно один верный вариант.', None
        return True, None, rows

    # --- Существующие маршруты ---
    @app.route('/')
    @app.route('/index')
    def index():
        courses = Course.query.all()
        announcements = []
        if current_user.is_authenticated:
            announcements = (
                Announcement.query.options(joinedload(Announcement.author))
                .order_by(Announcement.created_at.desc())
                .limit(50)
                .all()
            )
        return render_template(
            'index1.html',
            title='Главная',
            courses=courses,
            announcements=announcements,
            public_teachers=public_teachers_list(),
        )

    @app.route('/teachers/<slug>')
    def teacher_profile(slug):
        teacher = PUBLIC_TEACHERS.get(slug)
        if not teacher:
            abort(404)
        return render_template(
            'teacher_profile.html',
            title=teacher['full_name'],
            teacher=teacher,
        )

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user is None or not user.check_password(form.password.data):
                flash('Неверное имя пользователя или пароль', 'danger')
                return redirect(url_for('login'))
            if getattr(user, 'is_active', True) is False:
                flash('Аккаунт деактивирован. Обратитесь к администратору.', 'danger')
                return redirect(url_for('login'))
            try:
                user.last_login_at = datetime.utcnow()
                db.session.add(LoginEvent(user_id=user.id, ip_address=request.remote_addr))
                db.session.commit()
            except Exception:
                db.session.rollback()
            login_user(user, remember=form.remember_me.data)
            return redirect(url_for('index'))
        return render_template('login.html', title='Вход', form=form)

    @app.route('/logout')
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        if not current_app.config.get('ALLOW_PUBLIC_REGISTRATION', True):
            flash('Регистрация отключена. Обратитесь к администратору.', 'warning')
            return redirect(url_for('login'))
        form = RegistrationForm()
        if form.validate_on_submit():
            if is_reserved_username(form.username.data):
                flash('Это имя пользователя зарезервировано.', 'danger')
                return render_template('register.html', title='Регистрация', form=form)
            try:
                user = User(username=form.username.data, email=form.email.data)
                user.set_password(form.password.data)
                db.session.add(user)
                db.session.commit()
                flash('Вы успешно зарегистрировались!', 'success')
                return redirect(url_for('login'))
            except IntegrityError:
                db.session.rollback()
                flash('Ошибка: имя пользователя или email уже заняты.', 'danger')
        return render_template('register.html', title='Регистрация', form=form)

    # --- Маршруты для тестов ---
    @app.route('/tests')
    def tests():
        tests = Test.query.all()
        return render_template('tests/tests.html', title='Тесты', tests=tests)

    @app.route('/course/<int:course_id>/tests')
    def course_tests(course_id):
        course = Course.query.get_or_404(course_id)
        tests = Test.query.filter_by(course_id=course_id).all()
        return render_template('tests/course_tests.html', title=f'Тесты курса "{course.title}"', course=course, tests=tests)

    @app.route('/test/create', methods=['GET', 'POST'])
    @login_required
    def create_test():
        access_redirect = ensure_test_management_access()
        if access_redirect:
            return access_redirect

        form = TestForm()
        courses = list(teacher_courses_query().all()) if current_user.role == 'teacher' else list(Course.query.order_by(Course.title).all())
        if not courses:
            flash('Сначала создайте хотя бы один курс (в кабинете учителя), затем можно создавать тесты.', 'warning')
            return redirect(url_for('teacher_dashboard') if current_user.role == 'teacher' else url_for('tests'))
        form.course_id.choices = [(course.id, course.title) for course in courses]

        preselected_course_id = request.args.get('course_id', type=int)
        if request.method == 'GET' and preselected_course_id and any(c.id == preselected_course_id for c in courses):
            form.course_id.data = preselected_course_id

        if form.validate_on_submit():
            chosen = Course.query.get(form.course_id.data)
            if not teacher_manages_course(chosen):
                flash('Нет доступа к выбранному курсу.', 'danger')
                return redirect(url_for('create_test'))
            test = Test(
                title=form.title.data,
                description=form.description.data,
                course_id=form.course_id.data
            )
            db.session.add(test)
            db.session.commit()
            flash('Тест создан. Добавьте вопросы на странице редактирования.', 'success')
            return redirect(url_for('edit_test', test_id=test.id))
        return render_template('tests/create_test.html', title='Создать тест', form=form)

    @app.route('/test/<int:test_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_test(test_id):
        access_redirect = ensure_test_management_access()
        if access_redirect:
            return access_redirect
        test = Test.query.get_or_404(test_id)
        if not test.course or not teacher_manages_course(test.course):
            abort(403)
        qform = QuestionBuilderForm()
        if request.method == 'GET' and len(qform.options) < 4:
            while len(qform.options) < 4:
                qform.options.append_entry()
        if qform.validate_on_submit():
            ok, err, rows = _validate_question_builder(qform)
            if not ok:
                flash(err, 'danger')
            else:
                q = Question(
                    text=qform.text.data.strip(),
                    test_id=test.id,
                    question_type=qform.question_type.data,
                )
                db.session.add(q)
                db.session.flush()
                for text, is_correct in rows:
                    db.session.add(Option(text=text, is_correct=is_correct, question_id=q.id))
                db.session.commit()
                flash('Вопрос добавлен.', 'success')
                return redirect(url_for('edit_test', test_id=test.id))
        return render_template(
            'tests/edit_test.html',
            title=f'Редактирование: {test.title}',
            test=test,
            qform=qform,
        )

    @app.route('/test/<int:test_id>/question/<int:question_id>/delete', methods=['POST'])
    @login_required
    def delete_question(test_id, question_id):
        access_redirect = ensure_test_management_access()
        if access_redirect:
            return access_redirect
        test = Test.query.get_or_404(test_id)
        if not test.course or not teacher_manages_course(test.course):
            abort(403)
        question = Question.query.filter_by(id=question_id, test_id=test.id).first_or_404()
        db.session.delete(question)
        db.session.commit()
        flash('Вопрос удалён.', 'info')
        return redirect(url_for('edit_test', test_id=test.id))

    @app.route('/test/<int:test_id>')
    def view_test(test_id):
        test = Test.query.get_or_404(test_id)
        return render_template('tests/view_test.html', title=test.title, test=test)

    @app.route('/test/<int:test_id>/take', methods=['GET', 'POST'])
    @login_required
    def take_test(test_id):
        test = Test.query.get_or_404(test_id)
        if not user_can_take_test(test):
            abort(403)
        if request.method == 'POST':
            if not test.questions:
                flash('В этом тесте нет вопросов!', 'warning')
                return redirect(url_for('view_test', test_id=test.id))

            for question in test.questions:
                qtype = question.question_type or 'single_choice'
                if qtype == 'file_upload':
                    f = request.files.get(f'file_question_{question.id}')
                    if not f or not f.filename:
                        flash('Прикрепите файл для всех вопросов с ответом сканом или фото.', 'warning')
                        return redirect(url_for('take_test', test_id=test.id))
                elif qtype == 'text_answer':
                    if not (request.form.get(f'question_{question.id}') or '').strip():
                        flash('Заполните текстовый ответ для всех соответствующих вопросов.', 'warning')
                        return redirect(url_for('take_test', test_id=test.id))

            gradable = [
                q for q in test.questions
                if (q.question_type or 'single_choice') in (
                    'single_choice', 'multiple_choice', 'text_answer',
                )
            ]
            score = 0
            for question in gradable:
                qtype = question.question_type or 'single_choice'
                if qtype == 'text_answer':
                    user_answer = _normalize_text_answer(
                        request.form.get(f'question_{question.id}')
                    )
                    correct_answers = {
                        _normalize_text_answer(o.text)
                        for o in question.options if o.is_correct
                    }
                    if user_answer and user_answer in correct_answers:
                        score += 1
                elif qtype == 'single_choice':
                    user_answer = request.form.get(f'question_{question.id}')
                    if not user_answer:
                        continue
                    try:
                        chosen_id = int(user_answer)
                    except (TypeError, ValueError):
                        continue
                    correct_ids = {o.id for o in question.options if o.is_correct}
                    if len(correct_ids) == 1 and chosen_id in correct_ids:
                        score += 1
                else:
                    selected = {int(x) for x in request.form.getlist(f'question_{question.id}') if x.isdigit()}
                    correct_ids = {o.id for o in question.options if o.is_correct}
                    if correct_ids and selected == correct_ids:
                        score += 1

            total_questions = len(gradable)
            result = TestResult(
                user_id=current_user.id,
                test_id=test.id,
                score=score,
                total_questions=total_questions,
            )
            db.session.add(result)
            db.session.flush()

            for question in test.questions:
                qtype = question.question_type or 'single_choice'
                if qtype != 'file_upload':
                    continue
                f = request.files.get(f'file_question_{question.id}')
                rel_path, _ = save_submission_file(
                    f, prefix=f'tr{result.id}_q{question.id}_',
                )
                if not rel_path:
                    db.session.rollback()
                    flash(
                        'Недопустимый тип файла для ответа. Разрешены: PDF, Word, изображения, TXT.',
                        'danger',
                    )
                    return redirect(url_for('take_test', test_id=test.id))
                db.session.add(QuestionFileSubmission(
                    test_result_id=result.id,
                    question_id=question.id,
                    file_path=rel_path,
                ))

            db.session.commit()
            return redirect(url_for('test_result', result_id=result.id))
        return render_template('tests/take_test.html', title=f'Прохождение теста: {test.title}', test=test)

    @app.route('/test/result/<int:result_id>')
    @login_required
    def test_result(result_id):
        result = TestResult.query.get_or_404(result_id)
        if result.user_id != current_user.id:
            abort(403)
        return render_template('tests/result.html', title='Результат теста', result=result)

    @app.route('/question/create')
    @login_required
    def create_question():
        access_redirect = ensure_test_management_access()
        if access_redirect:
            return access_redirect
        tid = request.args.get('test_id', type=int)
        if tid:
            return redirect(url_for('edit_test', test_id=tid))
        flash('Выберите тест и откройте его редактирование, чтобы добавить вопросы.', 'info')
        return redirect(url_for('tests'))

    @app.route('/option/create')
    @login_required
    def create_option():
        access_redirect = ensure_test_management_access()
        if access_redirect:
            return access_redirect
        tid = request.args.get('test_id', type=int)
        if tid:
            return redirect(url_for('edit_test', test_id=tid))
        flash('Варианты ответов добавляются в конструкторе теста.', 'info')
        return redirect(url_for('tests'))

    # Личный кабинет
    @app.route('/profile')
    @login_required
    def profile():
        user_course = current_user.user_courses[0] if current_user.user_courses else None
        if not user_course:
            return render_template('profile.html', user_course=None, progress=0)

        course = user_course.course

        # Вычисляем прогресс
        total_tests = Test.query.filter_by(course_id=course.id).count()
        completed_tests = TestResult.query.filter(
            TestResult.user_id == current_user.id,
            TestResult.test_id.in_([test.id for test in Test.query.filter_by(course_id=course.id).all()])
        ).count()

        total_homeworks = Homework.query.filter_by(course_id=course.id).count()
        completed_homeworks = 0

        # Считаем выполненные ДЗ (тесты без прикрепления файла)
        completed_homeworks += TestResult.query.join(Test).join(Homework, Homework.test_id == Test.id).filter(
            Test.is_homework == True,
            Homework.is_essay == False,
            TestResult.user_id == current_user.id,
            Test.course_id == course.id
        ).count()

        # Считаем выполненные ДЗ с прикреплением файла (проверенные учителем)
        completed_homeworks += HomeworkSubmission.query.filter(
            HomeworkSubmission.user_id == current_user.id,
            HomeworkSubmission.homework_id.in_([hw.id for hw in Homework.query.filter_by(course_id=course.id, is_essay=True).all()]),
            HomeworkSubmission.is_approved == True
        ).count()

        total = total_tests + total_homeworks
        progress = (completed_tests + completed_homeworks) / total * 100 if total > 0 else 0

        return render_template('profile.html', user_course=user_course, progress=progress)

    # Домашние задания
    @app.route('/homeworks')
    @login_required
    def homeworks():
        user_course = current_user.user_courses[0] if current_user.user_courses else None
        if not user_course:
            flash('Вы не записаны ни на один курс.', 'warning')
            return redirect(url_for('profile'))

        homeworks = Homework.query.filter_by(course_id=user_course.course.id).all()
        return render_template('homeworks.html', homeworks=homeworks)

    # Прикрепление файла к домашнему заданию
    @app.route('/download/material/<int:material_id>')
    @login_required
    def download_course_material(material_id):
        mat = CourseMaterial.query.get_or_404(material_id)
        if not can_access_course_material(mat, current_user):
            abort(403)
        abs_path = upload_abs_path(mat.file_path)
        if not abs_path or not os.path.isfile(abs_path):
            abort(404)
        directory = os.path.dirname(abs_path)
        return send_from_directory(directory, os.path.basename(abs_path), as_attachment=True)

    @app.route('/download/homework/<int:submission_id>')
    @login_required
    def download_homework_submission(submission_id):
        sub = HomeworkSubmission.query.get_or_404(submission_id)
        if not can_access_homework_submission(sub, current_user):
            abort(403)
        abs_path = upload_abs_path(sub.file_path)
        if not abs_path or not os.path.isfile(abs_path):
            abort(404)
        directory = os.path.dirname(abs_path)
        return send_from_directory(directory, os.path.basename(abs_path), as_attachment=True)

    @app.route('/download/test-answer/<int:submission_id>')
    @login_required
    def download_test_answer_submission(submission_id):
        sub = QuestionFileSubmission.query.get_or_404(submission_id)
        if not can_access_test_file_submission(sub, current_user):
            abort(403)
        abs_path = upload_abs_path(sub.file_path)
        if not abs_path or not os.path.isfile(abs_path):
            abort(404)
        directory = os.path.dirname(abs_path)
        return send_from_directory(directory, os.path.basename(abs_path), as_attachment=True)

    @app.route('/homework/<int:homework_id>/submit', methods=['GET', 'POST'])
    @login_required
    def submit_homework(homework_id):
        homework = Homework.query.get_or_404(homework_id)
        if not homework.course_id or not student_enrolled(homework.course_id):
            abort(403)
        if not homework.is_essay:
            flash('Это задание не требует прикрепления файла.', 'warning')
            return redirect(url_for('homeworks'))

        if request.method == 'POST':
            file = request.files.get('file')
            if file and file.filename != '':
                file_path, _ = save_submission_file(
                    file, prefix=f'hw{homework_id}_u{current_user.id}_',
                )
                if not file_path:
                    flash(
                        'Недопустимый тип файла. Разрешены: PDF, Word, изображения, TXT.',
                        'danger',
                    )
                    return redirect(url_for('submit_homework', homework_id=homework_id))

                # Сохраняем информацию о файле в базе
                submission = HomeworkSubmission.query.filter_by(
                    user_id=current_user.id,
                    homework_id=homework_id
                ).first()
                if not submission:
                    submission = HomeworkSubmission(
                        user_id=current_user.id,
                        homework_id=homework_id,
                        file_path=file_path
                    )
                    db.session.add(submission)
                else:
                    submission.file_path = file_path
                    submission.is_rejected = False
                    submission.rejection_reason = None
                db.session.commit()
                flash('Файл загружен! Ожидайте проверки учителем.', 'success')
                return redirect(url_for('homeworks'))

        existing_submission = HomeworkSubmission.query.filter_by(
            user_id=current_user.id,
            homework_id=homework_id,
        ).first()
        return render_template(
            'submit_homework.html',
            homework=homework,
            existing_submission=existing_submission,
        )

    # Расписание
    @app.route('/schedule')
    @login_required
    def schedule():
        week = request.args.get('week', 1, type=int)
        user_course = current_user.user_courses[0] if current_user.user_courses else None
        if not user_course:
            flash('Вы не записаны ни на один курс.', 'warning')
            return redirect(url_for('profile'))

        schedule = Schedule.query.filter_by(
            course_id=user_course.course.id,
            week_number=week
        ).order_by(Schedule.start_time).all()

        return render_template('schedule.html', schedule=schedule, current_week=week)

    # --- Материалы курса (студенты) ---
    @app.route('/course/<int:course_id>/materials')
    @login_required
    def course_materials(course_id):
        course = Course.query.get_or_404(course_id)
        can_manage = teacher_manages_course(course)
        rows = CourseMaterial.query.filter_by(course_id=course_id).order_by(
            CourseMaterial.sort_order, CourseMaterial.id
        ).all()
        visible = []
        for m in rows:
            if m.course_students_only:
                if can_manage or student_enrolled(course_id):
                    visible.append(m)
            else:
                visible.append(m)
        for m in visible:
            m._static_rel = static_file_relative(m.file_path)
            m._file_label = material_file_label(m.file_path)
            if current_user.is_authenticated and current_user.role == 'student':
                db.session.add(MaterialView(user_id=current_user.id, material_id=m.id))
        if current_user.is_authenticated:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        return render_template(
            'course/materials.html',
            title=f'Материалы: {course.title}',
            course=course,
            materials=visible,
            can_manage=can_manage,
        )

    # --- Кабинет учителя ---
    @app.route('/teacher', methods=['GET', 'POST'])
    @login_required
    def teacher_dashboard():
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        ann_form = AnnouncementForm()
        if request.method == 'POST' and ann_form.validate_on_submit():
            db.session.add(Announcement(
                title=ann_form.title.data.strip(),
                body=ann_form.body.data.strip(),
                author_id=current_user.id,
            ))
            db.session.commit()
            flash('Объявление опубликовано.', 'success')
            return redirect(url_for('teacher_dashboard'))
        courses = teacher_courses_query().all()
        pending_files = (
            QuestionFileSubmission.query.join(TestResult)
            .join(Test, Test.id == TestResult.test_id)
            .join(Course, Course.id == Test.course_id)
            .filter(QuestionFileSubmission.is_reviewed.is_(False))
        )
        if current_user.role == 'teacher':
            pending_files = pending_files.filter(Course.author_id == current_user.id)
        pending_count = pending_files.count()
        pending_hw = (
            HomeworkSubmission.query.join(Homework)
            .join(Course, Course.id == Homework.course_id)
            .filter(
                HomeworkSubmission.is_approved.is_(False),
                HomeworkSubmission.is_rejected.is_(False),
            )
        )
        if current_user.role == 'teacher':
            pending_hw = pending_hw.filter(Course.author_id == current_user.id)
        pending_hw_count = pending_hw.count()
        return render_template(
            'teacher/dashboard.html',
            title='Кабинет учителя',
            courses=courses,
            pending_file_reviews=pending_count,
            pending_homework_reviews=pending_hw_count,
            ann_form=ann_form,
        )

    @app.route('/teacher/reviews')
    @login_required
    def teacher_file_reviews():
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        q = (
            QuestionFileSubmission.query.join(TestResult)
            .join(Test, Test.id == TestResult.test_id)
            .join(Course, Course.id == Test.course_id)
            .join(Question, Question.id == QuestionFileSubmission.question_id)
        )
        if current_user.role == 'teacher':
            q = q.filter(Course.author_id == current_user.id)
        status = request.args.get('status', 'pending')
        if status == 'pending':
            q = q.filter(QuestionFileSubmission.is_reviewed.is_(False))
        elif status == 'done':
            q = q.filter(QuestionFileSubmission.is_reviewed.is_(True))
        elif status != 'all':
            status = 'pending'
            q = q.filter(QuestionFileSubmission.is_reviewed.is_(False))
        rows = q.order_by(QuestionFileSubmission.submitted_at.desc()).all()
        for s in rows:
            s._static_rel = static_file_relative(s.file_path)
        return render_template(
            'teacher/reviews.html',
            title='Проверка ответов (файлы)',
            submissions=rows,
            status=status,
        )

    @app.route('/teacher/reviews/<int:submission_id>', methods=['GET', 'POST'])
    @login_required
    def teacher_file_review_detail(submission_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        sub = QuestionFileSubmission.query.get_or_404(submission_id)
        tr = sub.test_result
        test = tr.test
        course = test.course if test else None
        if not course or not teacher_manages_course(course):
            abort(403)
        form = FileReviewForm()
        if request.method == 'POST' and form.validate_on_submit():
            sub.is_reviewed = True
            sub.reviewed_at = datetime.utcnow()
            sub.reviewed_by_id = current_user.id
            sub.teacher_comment = (form.teacher_comment.data or '').strip() or None
            db.session.commit()
            flash('Ответ отмечен как проверенный.', 'success')
            return redirect(url_for('teacher_file_reviews'))
        if request.method == 'GET':
            form.teacher_comment.data = sub.teacher_comment
        return render_template(
            'teacher/review_detail.html',
            title='Проверка ответа',
            submission=sub,
            test=test,
            course=course,
            student=tr.user,
            question=sub.question,
            static_rel=static_file_relative(sub.file_path),
            form=form,
        )

    @app.route('/teacher/courses')
    @login_required
    def teacher_courses():
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        courses = teacher_courses_query().all()
        return render_template('teacher/courses.html', title='Мои курсы', courses=courses)

    @app.route('/teacher/course/new', methods=['GET', 'POST'])
    @login_required
    def teacher_course_new():
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        form = CourseForm()
        if form.validate_on_submit():
            c = Course(
                title=form.title.data.strip(),
                description=(form.description.data or '').strip() or None,
                author_id=current_user.id,
            )
            db.session.add(c)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('Курс с таким названием уже существует.', 'danger')
                return redirect(url_for('teacher_course_new'))
            flash('Курс создан.', 'success')
            return redirect(url_for('teacher_course_hub', course_id=c.id))
        return render_template('teacher/course_form.html', title='Новый курс', form=form)

    @app.route('/teacher/course/<int:course_id>/edit', methods=['GET', 'POST'])
    @login_required
    def teacher_course_edit(course_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        form = CourseForm(obj=course)
        if form.validate_on_submit():
            course.title = form.title.data.strip()
            course.description = (form.description.data or '').strip() or None
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('Курс с таким названием уже существует.', 'danger')
                return redirect(url_for('teacher_course_edit', course_id=course_id))
            flash('Курс сохранён.', 'success')
            return redirect(url_for('teacher_course_hub', course_id=course.id))
        return render_template('teacher/course_form.html', title='Редактирование курса', form=form, course=course)

    @app.route('/teacher/course/<int:course_id>')
    @login_required
    def teacher_course_hub(course_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        tests = Test.query.filter_by(course_id=course.id).order_by(Test.title).all()
        return render_template(
            'teacher/course_hub.html',
            title=course.title,
            course=course,
            tests=tests,
        )

    @app.route('/teacher/course/<int:course_id>/materials', methods=['GET', 'POST'])
    @login_required
    def teacher_course_materials(course_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        form = CourseMaterialForm()
        materials = CourseMaterial.query.filter_by(course_id=course.id).order_by(
            CourseMaterial.sort_order, CourseMaterial.id
        ).all()
        if request.method == 'POST' and form.validate_on_submit():
            url = (form.external_url.data or '').strip() or None
            if url and not is_safe_external_url(url):
                flash('Ссылка должна начинаться с http:// или https://', 'danger')
                return redirect(url_for('teacher_course_materials', course_id=course.id))
            up = request.files.get('material_file')
            rel = None
            if up and up.filename:
                safe = safe_material_storage_name(up.filename)
                if not safe:
                    allowed = ', '.join(sorted(ALLOWED_MATERIAL_EXTENSIONS))
                    flash(
                        f'Недопустимый тип файла. Разрешены: {allowed}',
                        'warning',
                    )
                    return redirect(url_for('teacher_course_materials', course_id=course.id))
                upload_dir = os.path.join('app', 'static', 'uploads', 'materials')
                os.makedirs(upload_dir, exist_ok=True)
                fname = f"c{course_id}_{safe}"
                dest = os.path.join(upload_dir, fname)
                up.save(dest)
                rel = f"uploads/materials/{fname}"
            if not url and not rel:
                flash('Укажите ссылку или загрузите файл.', 'danger')
                return redirect(url_for('teacher_course_materials', course_id=course.id))
            mx = db.session.query(func.max(CourseMaterial.sort_order)).filter_by(course_id=course.id).scalar()
            nxt = (mx or 0) + 1
            mat = CourseMaterial(
                course_id=course.id,
                title=form.title.data.strip(),
                description=(form.description.data or '').strip() or None,
                file_path=rel,
                external_url=url,
                course_students_only=bool(form.course_students_only.data),
                sort_order=nxt,
            )
            db.session.add(mat)
            db.session.commit()
            flash('Материал добавлен.', 'success')
            return redirect(url_for('teacher_course_materials', course_id=course.id))
        for m in materials:
            m._static_rel = static_file_relative(m.file_path)
            m._file_label = material_file_label(m.file_path)
        return render_template(
            'teacher/course_materials.html',
            title=f'Материалы: {course.title}',
            course=course,
            materials=materials,
            form=form,
        )

    @app.route('/teacher/course/<int:course_id>/materials/<int:material_id>/delete', methods=['POST'])
    @login_required
    def teacher_course_material_delete(course_id, material_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        mat = CourseMaterial.query.filter_by(id=material_id, course_id=course.id).first_or_404()
        db.session.delete(mat)
        db.session.commit()
        flash('Материал удалён.', 'info')
        return redirect(url_for('teacher_course_materials', course_id=course.id))

    @app.route('/teacher/course/<int:course_id>/schedule', methods=['GET', 'POST'])
    @login_required
    def teacher_course_schedule(course_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        week = request.args.get('week', 1, type=int)
        form = ScheduleLessonForm()
        if request.method == 'POST' and form.validate_on_submit():
            st = parse_iso_datetime(form.start_time.data)
            en = parse_iso_datetime(form.end_time.data)
            try:
                wn = int(form.week_number.data)
            except (TypeError, ValueError):
                wn = week
            if not st or not en:
                flash('Неверный формат даты и времени.', 'danger')
            else:
                db.session.add(Schedule(
                    course_id=course.id,
                    start_time=st,
                    end_time=en,
                    topic=form.topic.data.strip(),
                    week_number=wn,
                ))
                db.session.commit()
                flash('Занятие добавлено.', 'success')
            return redirect(url_for('teacher_course_schedule', course_id=course.id, week=week))
        lessons = Schedule.query.filter_by(course_id=course.id, week_number=week).order_by(
            Schedule.start_time
        ).all()
        return render_template(
            'teacher/course_schedule.html',
            title=f'Расписание: {course.title}',
            course=course,
            lessons=lessons,
            current_week=week,
            form=form,
        )

    @app.route('/teacher/course/<int:course_id>/schedule/<int:lesson_id>/delete', methods=['POST'])
    @login_required
    def teacher_course_schedule_delete(course_id, lesson_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        lesson = Schedule.query.filter_by(id=lesson_id, course_id=course.id).first_or_404()
        wk = lesson.week_number
        db.session.delete(lesson)
        db.session.commit()
        flash('Запись удалена.', 'info')
        return redirect(url_for('teacher_course_schedule', course_id=course.id, week=wk))

    @app.route('/teacher/course/<int:course_id>/homeworks', methods=['GET', 'POST'])
    @login_required
    def teacher_course_homeworks(course_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        tests = Test.query.filter_by(course_id=course.id).order_by(Test.title).all()
        form = HomeworkManageForm()
        form.test_id.choices = [(0, '— без привязки к тесту —')] + [(t.id, t.title) for t in tests]
        if request.method == 'POST' and form.validate_on_submit():
            tid = form.test_id.data if form.test_id.data else 0
            if tid and not any(t.id == tid for t in tests):
                flash('Неверный тест.', 'danger')
            else:
                dl = parse_iso_datetime(form.deadline.data) if form.deadline.data else None
                hw = Homework(
                    title=form.title.data.strip(),
                    description=(form.description.data or '').strip() or None,
                    course_id=course.id,
                    test_id=tid if tid else None,
                    is_essay=bool(form.is_essay.data),
                    deadline=dl,
                )
                db.session.add(hw)
                db.session.commit()
                flash('Домашнее задание создано.', 'success')
            return redirect(url_for('teacher_course_homeworks', course_id=course.id))
        homeworks = Homework.query.filter_by(course_id=course.id).order_by(Homework.id.desc()).all()
        return render_template(
            'teacher/course_homeworks.html',
            title=f'Домашние задания: {course.title}',
            course=course,
            homeworks=homeworks,
            form=form,
        )

    @app.route('/teacher/homework/<int:homework_id>/submissions')
    @login_required
    def teacher_homework_submissions(homework_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        hw = Homework.query.get_or_404(homework_id)
        if not hw.course or not teacher_manages_course(hw.course):
            abort(403)
        subs = HomeworkSubmission.query.filter_by(homework_id=hw.id).order_by(HomeworkSubmission.id.desc()).all()
        for s in subs:
            s._static_rel = static_file_relative(s.file_path)
        return render_template(
            'teacher/homework_submissions.html',
            title=f'Сдачи: {hw.title}',
            homework=hw,
            submissions=subs,
        )

    @app.route('/teacher/homework-submission/<int:submission_id>/approve', methods=['POST'])
    @login_required
    def teacher_homework_submission_approve(submission_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        sub = HomeworkSubmission.query.get_or_404(submission_id)
        hw = sub.homework
        if not hw.course or not teacher_manages_course(hw.course):
            abort(403)
        sub.is_approved = True
        sub.is_rejected = False
        sub.rejection_reason = None
        db.session.commit()
        flash('Работа отмечена как проверенная.', 'success')
        return redirect(url_for('teacher_homework_submissions', homework_id=hw.id))

    @app.route('/teacher/homework-submission/<int:submission_id>/reject', methods=['POST'])
    @login_required
    def teacher_homework_submission_reject(submission_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        sub = HomeworkSubmission.query.get_or_404(submission_id)
        hw = sub.homework
        if not hw.course or not teacher_manages_course(hw.course):
            abort(403)
        form = HomeworkRejectForm()
        if not form.validate_on_submit():
            flash('Укажите причину отклонения.', 'danger')
            return redirect(url_for('teacher_homework_submissions', homework_id=hw.id))
        sub.is_approved = False
        sub.is_rejected = True
        sub.rejection_reason = form.rejection_reason.data.strip()
        db.session.commit()
        flash('Работа отклонена. Студент увидит ваш комментарий.', 'info')
        return redirect(url_for('teacher_homework_submissions', homework_id=hw.id))

    @app.route('/teacher/homework-submission/<int:submission_id>/unapprove', methods=['POST'])
    @login_required
    def teacher_homework_submission_unapprove(submission_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        sub = HomeworkSubmission.query.get_or_404(submission_id)
        hw = sub.homework
        if not hw.course or not teacher_manages_course(hw.course):
            abort(403)
        sub.is_approved = False
        sub.is_rejected = False
        sub.rejection_reason = None
        db.session.commit()
        flash('Отметка проверки снята.', 'info')
        return redirect(url_for('teacher_homework_submissions', homework_id=hw.id))

    @app.route('/parent')
    @login_required
    def parent_dashboard():
        redir = ensure_parent()
        if redir:
            return redir
        children = User.query.filter_by(parent_guardian_id=current_user.id).order_by(User.username).all()
        student_id = request.args.get('student_id', type=int)
        student = None
        if student_id:
            student = User.query.filter_by(id=student_id, parent_guardian_id=current_user.id).first()
        if not student and children:
            student = children[0]

        attendance_labels = {'present': 'Присутствие', 'absent': 'Отсутствие', 'late': 'Опоздание'}
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        month_end = datetime(now.year + 1, 1, 1) if now.month == 12 else datetime(now.year, now.month + 1, 1)
        week_end = now + timedelta(days=7)

        recent_attendance = []
        absence_count_month = 0
        upcoming_lessons = []
        next_lesson = None
        pending_homework_rows = []
        overall_progress = 0.0
        progress_has_data = False
        stat_pending_hw = 0
        stat_upcoming = 0

        def course_has_measurable_work(course):
            if not course:
                return False
            n_tests = Test.query.filter_by(course_id=course.id).count()
            n_hw = Homework.query.filter_by(course_id=course.id).count()
            return (n_tests + n_hw) > 0

        if student:
            recent_attendance = (
                Attendance.query.filter_by(user_id=student.id)
                .join(Schedule, Attendance.schedule_id == Schedule.id)
                .order_by(Schedule.start_time.desc())
                .limit(30)
                .all()
            )
            absence_count_month = (
                Attendance.query.join(Schedule, Attendance.schedule_id == Schedule.id)
                .filter(
                    Attendance.user_id == student.id,
                    Attendance.status == 'absent',
                    Schedule.start_time >= month_start,
                    Schedule.start_time < month_end,
                )
                .count()
            )
            course_ids = [uc.course_id for uc in student.user_courses]
            if course_ids:
                upcoming_lessons = (
                    Schedule.query.filter(
                        Schedule.course_id.in_(course_ids),
                        Schedule.start_time >= now,
                        Schedule.start_time < week_end,
                    )
                    .order_by(Schedule.start_time)
                    .all()
                )
                stat_upcoming = len(upcoming_lessons)
                if stat_upcoming == 0:
                    next_lesson = (
                        Schedule.query.filter(
                            Schedule.course_id.in_(course_ids),
                            Schedule.start_time >= now,
                        )
                        .order_by(Schedule.start_time.asc())
                        .first()
                    )
                for uc in student.user_courses:
                    course = uc.course
                    q = Homework.query.filter_by(course_id=course.id).order_by(
                        nullslast(Homework.deadline.asc()), Homework.id
                    )
                    for hw in q.all():
                        if not homework_done_for_user(student.id, course.id, hw):
                            pending_homework_rows.append({'homework': hw, 'course': course})
                stat_pending_hw = len(pending_homework_rows)
            percents = []
            for uc in student.user_courses:
                if not uc.course:
                    continue
                if course_has_measurable_work(uc.course):
                    progress_has_data = True
                    percents.append(progress_percent_for_course(student.id, uc.course))
            overall_progress = sum(percents) / len(percents) if percents else 0.0

        return render_template(
            'parent/dashboard.html',
            title='Кабинет родителя',
            children=children,
            student=student,
            recent_attendance=recent_attendance,
            absence_count_month=absence_count_month,
            upcoming_lessons=upcoming_lessons,
            next_lesson=next_lesson,
            pending_homework_rows=pending_homework_rows,
            overall_progress=overall_progress,
            progress_has_data=progress_has_data,
            attendance_labels=attendance_labels,
            stat_pending_hw=stat_pending_hw,
            stat_upcoming=stat_upcoming,
            now=now,
        )

    @app.route('/teacher/course/<int:course_id>/schedule/<int:lesson_id>/attendance', methods=['GET', 'POST'])
    @login_required
    def teacher_course_lesson_attendance(course_id, lesson_id):
        redir = ensure_teacher_or_admin()
        if redir:
            return redir
        course = Course.query.get_or_404(course_id)
        if not teacher_manages_course(course):
            abort(403)
        lesson = Schedule.query.filter_by(id=lesson_id, course_id=course.id).first_or_404()
        enrollments = UserCourse.query.filter_by(course_id=course.id).all()
        students = [e.user for e in enrollments if e.user]

        if request.method == 'POST':
            for u in students:
                raw = (request.form.get(f'status_{u.id}') or '').strip()
                if raw not in ('present', 'absent', 'late'):
                    continue
                row = Attendance.query.filter_by(user_id=u.id, schedule_id=lesson.id).first()
                if row:
                    row.status = raw
                else:
                    db.session.add(
                        Attendance(user_id=u.id, schedule_id=lesson.id, status=raw)
                    )
            db.session.commit()
            flash('Посещаемость сохранена.', 'success')
            return redirect(
                url_for('teacher_course_schedule', course_id=course.id, week=lesson.week_number)
            )

        existing = {
            a.user_id: a.status
            for a in Attendance.query.filter_by(schedule_id=lesson.id).all()
        }
        return render_template(
            'teacher/course_attendance.html',
            title=f'Посещаемость: {lesson.topic}',
            course=course,
            lesson=lesson,
            students=students,
            existing_status=existing,
        )