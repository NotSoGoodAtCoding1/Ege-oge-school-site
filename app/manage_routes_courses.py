from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import User, Course, UserCourse, Test, TestResult, MaterialView, CourseMaterial
from app.forms import AdminCourseForm
from app.security import is_admin_user

def is_admin():
    return is_admin_user(current_user)

def register_course_routes(app):
    def guard():
        if not is_admin():
            flash('Admin only.', 'danger')
            return redirect(url_for('index'))

    def fill_course_form(form):
        teachers = User.query.filter(User.role.in_(('teacher', 'admin'))).order_by(User.username).all()
        form.author_id.choices = [(t.id, t.username) for t in teachers]
        form.teacher_ids.choices = form.author_id.choices

    def sync_teachers(course, extra_ids, primary):
        ids = set(extra_ids or [])
        if primary: ids.add(primary)
        course.assigned_teachers = User.query.filter(User.id.in_(ids)).all() if ids else []

    @app.route('/manage/courses')
    @login_required
    def admin_courses():
        if not is_admin(): return guard()
        return render_template('manage/courses.html', title='Courses', courses=Course.query.order_by(Course.title).all())

    @app.route('/manage/courses/new', methods=['GET','POST'])
    @app.route('/manage/courses/<int:course_id>/edit', methods=['GET','POST'])
    @login_required
    def admin_course_form(course_id=None):
        if not is_admin(): return guard()
        course = Course.query.get(course_id) if course_id else None
        form = AdminCourseForm()
        fill_course_form(form)
        if course and request.method == 'GET':
            form.title.data = course.title
            form.description.data = course.description
            form.subject.data = course.subject or ''
            form.school_class.data = course.school_class or ''
            form.author_id.data = course.author_id
            form.teacher_ids.data = [t.id for t in course.assigned_teachers if t.id != course.author_id]
        if form.validate_on_submit():
            if not course:
                course = Course()
                db.session.add(course)
            course.title = form.title.data.strip()
            course.description = (form.description.data or '').strip() or None
            course.subject = form.subject.data or None
            course.school_class = form.school_class.data or None
            course.author_id = form.author_id.data
            try:
                db.session.flush()
                sync_teachers(course, form.teacher_ids.data, form.author_id.data)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('Title exists.', 'danger')
                return render_template('manage/course_form.html', form=form, course=course, title='Course')
            return redirect(url_for('admin_courses'))
        return render_template('manage/course_form.html', form=form, course=course, title='Course')

    @app.route('/manage/courses/<int:course_id>/delete', methods=['POST'])
    @login_required
    def admin_course_delete(course_id):
        if not is_admin(): return guard()
        db.session.delete(Course.query.get_or_404(course_id))
        db.session.commit()
        return redirect(url_for('admin_courses'))

    @app.route('/manage/analytics')
    @login_required
    def admin_analytics():
        if not is_admin(): return guard()
        from datetime import datetime, timedelta
        from sqlalchemy import func
        from app.models import LoginEvent
        since = datetime.utcnow() - timedelta(days=14)
        rows = db.session.query(func.date(LoginEvent.logged_at), func.count(LoginEvent.id)).filter(
            LoginEvent.logged_at >= since).group_by(func.date(LoginEvent.logged_at)).all()
        labels, values = [str(r[0]) for r in rows], [r[1] for r in rows]
        stats = []
        for course in Course.query.order_by(Course.title).all():
            tids = [t.id for t in Test.query.filter_by(course_id=course.id).all()]
            stats.append(dict(course=course, enrolled=UserCourse.query.filter_by(course_id=course.id).count(),
                attempts=TestResult.query.filter(TestResult.test_id.in_(tids)).count() if tids else 0,
                views=MaterialView.query.join(CourseMaterial).filter(CourseMaterial.course_id==course.id).count()))
        return render_template('manage/analytics.html', title='Analytics', chart_labels=labels, chart_values=values, course_stats=stats)
