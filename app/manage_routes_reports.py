import csv
import io
from datetime import datetime
from flask import render_template, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from app.models import User, Course, TestResult, LoginEvent, Attendance, Schedule
from app.forms import AdminReportFilterForm
from app.security import is_admin_user

def is_admin():
    return is_admin_user(current_user)

def register_report_routes(app):
    def guard():
        if not is_admin():
            flash('Admin only.', 'danger')
            return redirect(url_for('index'))

    @app.route('/manage/reports', methods=['GET', 'POST'])
    @login_required
    def admin_reports():
        if not is_admin():
            return guard()
        form = AdminReportFilterForm()
        form.course_id.choices = [(0, 'All')] + [(c.id, c.title) for c in Course.query.order_by(Course.title).all()]
        form.teacher_id.choices = [(0, 'All')]
        if form.validate_on_submit():
            out = io.StringIO()
            w = csv.writer(out)
            if form.report_type.data == 'grades':
                w.writerow(['user', 'test', 'score', 'total'])
                for tr in TestResult.query.limit(5000).all():
                    w.writerow([tr.user.username, tr.test.title, tr.score, tr.total_questions])
            elif form.report_type.data == 'attendance':
                w.writerow(['user', 'course', 'topic', 'status'])
                for a in Attendance.query.join(Schedule).limit(5000).all():
                    w.writerow([a.user.username, a.schedule.course.title, a.schedule.topic, a.status])
            else:
                w.writerow(['user', 'event', 'at'])
                for ev in LoginEvent.query.order_by(LoginEvent.logged_at.desc()).limit(3000).all():
                    w.writerow([ev.user.username, 'login', ev.logged_at.isoformat()])
            return Response(out.getvalue(), mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=report.csv'})
        return render_template('manage/reports.html', title='Reports', form=form)
