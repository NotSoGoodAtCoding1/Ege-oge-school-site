import csv
import io
import re
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import User, Course, UserCourse, TestResult, LoginEvent, MaterialView, QuestionFileSubmission, HomeworkSubmission
from app.forms import AdminUserForm, AdminBulkImportForm
from app.security import is_admin_user, is_reserved_username, normalize_role

def is_admin():
    return is_admin_user(current_user)

def register_user_routes(app):
    def guard():
        if not is_admin():
            flash('Admin only.', 'danger')
            return redirect(url_for('index'))

    def sync_courses(user, ids):
        ids = set(ids or [])
        ex = {uc.course_id: uc for uc in user.user_courses}
        for cid in ids:
            if cid not in ex:
                db.session.add(UserCourse(user_id=user.id, course_id=cid, progress=0.0))
        for cid, uc in list(ex.items()):
            if cid not in ids:
                db.session.delete(uc)

    def fill_user_form(form):
        courses = [(c.id, c.title) for c in Course.query.order_by(Course.title).all()]
        form.course_ids.choices = courses
        form.teacher_course_ids.choices = courses
        parents = User.query.filter_by(role='parent').all()
        form.parent_guardian_id.choices = [(0, '-')] + [(p.id, p.username) for p in parents]

    @app.route('/manage')
    @login_required
    def admin_dashboard():
        if not is_admin():
            return guard()
        stats = dict(users=User.query.count(), students=User.query.filter_by(role='student').count(),
            courses=Course.query.count(), inactive=User.query.filter_by(is_active=False).count(),
            pending_files=QuestionFileSubmission.query.filter_by(is_reviewed=False).count(),
            pending_hw=HomeworkSubmission.query.filter_by(
                is_approved=False, is_rejected=False
            ).count())
        logins = LoginEvent.query.order_by(LoginEvent.logged_at.desc()).limit(8).all()
        return render_template('manage/dashboard.html', title='Admin', stats=stats, recent_logins=logins)

    @app.route('/manage/users')
    @login_required
    def admin_users():
        if not is_admin():
            return guard()
        q = User.query
        role, cls, search = request.args.get('role',''), request.args.get('class',''), (request.args.get('q') or '').strip()
        if role: q = q.filter_by(role=role)
        if cls: q = q.filter_by(school_class=cls)
        if search:
            like = f'%{search}%'
            q = q.filter(db.or_(User.username.ilike(like), User.email.ilike(like)))
        return render_template('manage/users.html', title='Users', users=q.order_by(User.id.desc()).all(),
            role=role, school_class=cls, search=search)

    @app.route('/manage/users/new', methods=['GET','POST'])
    @app.route('/manage/users/<int:user_id>/edit', methods=['GET','POST'])
    @login_required
    def admin_user_form(user_id=None):
        if not is_admin():
            return guard()
        user = User.query.get(user_id) if user_id else None
        form = AdminUserForm()
        fill_user_form(form)
        if user and request.method == 'GET':
            form.username.data, form.email.data = user.username, user.email
            form.full_name.data, form.phone.data = user.full_name, user.phone
            form.school_class.data, form.role.data = user.school_class or '', user.role
            form.is_active.data = getattr(user, 'is_active', True)
            form.course_ids.data = [uc.course_id for uc in user.user_courses]
            form.teacher_course_ids.data = [c.id for c in user.teaching_courses]
            form.parent_guardian_id.data = user.parent_guardian_id or 0
        if form.validate_on_submit():
            username = form.username.data.strip()
            if is_reserved_username(username) and (not user or user.username.lower() != username.lower()):
                flash('This username is reserved.', 'danger')
                return render_template('manage/user_form.html', form=form, user=user, title='User')
            if not user:
                if not form.password.data:
                    flash('Password required.', 'danger')
                    return render_template('manage/user_form.html', form=form, user=user, title='User')
                user = User()
                db.session.add(user)
            user.username = username
            user.email = form.email.data.strip().lower()
            user.full_name = (form.full_name.data or '').strip() or None
            user.phone = (form.phone.data or '').strip() or None
            user.school_class = form.school_class.data or None
            user.role = normalize_role(form.role.data)
            user.is_active = bool(form.is_active.data)
            user.parent_guardian_id = form.parent_guardian_id.data or None
            if user.parent_guardian_id == 0: user.parent_guardian_id = None
            if form.password.data: user.set_password(form.password.data)
            sync_courses(user, form.course_ids.data)
            user.teaching_courses = Course.query.filter(Course.id.in_(form.teacher_course_ids.data or [])).all() if user.role in ('teacher','admin') else []
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash('Login or email taken.', 'danger')
                return render_template('manage/user_form.html', form=form, user=user, title='User')
            return redirect(url_for('admin_user_detail', user_id=user.id))
        return render_template('manage/user_form.html', form=form, user=user, title='User')

    @app.route('/manage/users/<int:user_id>')
    @login_required
    def admin_user_detail(user_id):
        if not is_admin(): return guard()
        user = User.query.get_or_404(user_id)
        return render_template('manage/user_detail.html', title=user.username, user=user,
            logins=LoginEvent.query.filter_by(user_id=user.id).order_by(LoginEvent.logged_at.desc()).limit(20).all(),
            views=MaterialView.query.filter_by(user_id=user.id).order_by(MaterialView.viewed_at.desc()).limit(20).all(),
            results=TestResult.query.filter_by(user_id=user.id).order_by(TestResult.completed_at.desc()).limit(20).all(),
            courses=[uc.course for uc in user.user_courses])

    @app.route('/manage/users/<int:user_id>/deactivate', methods=['POST'])
    @login_required
    def admin_user_deactivate(user_id):
        if not is_admin(): return guard()
        u = User.query.get_or_404(user_id)
        if u.username != 'admin': u.is_active = False; db.session.commit()
        return redirect(url_for('admin_users'))

    @app.route('/manage/users/<int:user_id>/activate', methods=['POST'])
    @login_required
    def admin_user_activate(user_id):
        if not is_admin(): return guard()
        User.query.get_or_404(user_id).is_active = True; db.session.commit()
        return redirect(url_for('admin_users'))

    @app.route('/manage/users/import', methods=['GET','POST'])
    @login_required
    def admin_users_import():
        if not is_admin(): return guard()
        form = AdminBulkImportForm()
        if form.validate_on_submit():
            text = io.TextIOWrapper(form.file.data, encoding='utf-8-sig')
            created = 0
            for row in csv.DictReader(text):
                email = (row.get('email') or '').strip().lower()
                if not email or User.query.filter_by(email=email).first(): continue
                base = re.sub(r'[^a-zA-Z0-9_]','', email.split('@')[0].lower())[:40] or 'user'
                uname, n = base, 1
                while User.query.filter_by(username=uname).first(): uname = f'{base}{n}'; n += 1
                u = User(
                    username=uname,
                    email=email,
                    role=normalize_role(row.get('role')),
                    is_active=True,
                )
                u.set_password(form.default_password.data)
                db.session.add(u); db.session.flush(); created += 1
            db.session.commit()
            flash(f'Imported {created} users.', 'success')
            return redirect(url_for('admin_users'))
        return render_template('manage/users_import.html', title='Import', form=form)
