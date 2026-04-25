"""college_management_system URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path

from main_app.EditResultView import EditResultView

from . import assessment_views, billing_views, hod_views, staff_views, student_views, views

urlpatterns = [
    # Canonical dashboard entry URLs (same views as legacy routes; used for login + ACL messaging)
    path(
        "dashboard/super-admin/",
        hod_views.admin_home,
        name="superadmin_dashboard",
    ),
    path(
        "dashboard/admission/",
        staff_views.staff_course_students,
        name="admission_dashboard",
    ),
    path(
        "dashboard/instructor/",
        staff_views.staff_home,
        name="instructor_dashboard",
    ),
    path(
        "dashboard/student/",
        student_views.student_home,
        name="student_dashboard",
    ),
    path("", views.login_page, name='login_page'),
    path("get_attendance", views.get_attendance, name='get_attendance'),
    path("firebase-messaging-sw.js", views.showFirebaseJS, name='showFirebaseJS'),
    path("doLogin/", views.doLogin, name='user_login'),
    path("logout_user/", views.logout_user, name='user_logout'),
    path("sessions/active/", views.active_sessions, name="active_sessions"),
    path("admin/home/", hod_views.admin_home, name='admin_home'),
    path(
        "admin/admission-officers/",
        hod_views.manage_admission_officers,
        name="manage_admission_officers",
    ),
    path(
        "admin/admission-officers/add/",
        hod_views.add_admission_officer,
        name="add_admission_officer",
    ),
    path(
        "admin/admission-officers/<int:staff_id>/edit/",
        hod_views.edit_admission_officer,
        name="edit_admission_officer",
    ),
    path(
        "admin/admission-officers/<int:staff_id>/toggle/",
        hod_views.toggle_admission_officer_active,
        name="toggle_admission_officer_active",
    ),
    path(
        "admin/admission-officers/<int:staff_id>/delete/",
        hod_views.soft_delete_admission_officer,
        name="soft_delete_admission_officer",
    ),
    path("staff/add", hod_views.add_staff, name='add_staff'),
    path("course/add", hod_views.add_course, name='add_course'),
    path("send_student_notification/", hod_views.send_student_notification,
         name='send_student_notification'),
    path("send_staff_notification/", hod_views.send_staff_notification,
         name='send_staff_notification'),
    path("add_session/", hod_views.add_session, name='add_session'),
    path("admin_notify_student", hod_views.admin_notify_student,
         name='admin_notify_student'),
    path("admin_notify_staff", hod_views.admin_notify_staff,
         name='admin_notify_staff'),
    path("admin_view_profile", hod_views.admin_view_profile,
         name='admin_view_profile'),
    path("check_email_availability", hod_views.check_email_availability,
         name="check_email_availability"),
    path("session/manage/", hod_views.manage_session, name='manage_session'),
    path("session/set-active/<int:session_id>/",
         hod_views.set_active_session, name='set_active_session'),
    path("session/edit/<int:session_id>",
         hod_views.edit_session, name='edit_session'),
    path("student/view/feedback/", hod_views.student_feedback_message,
         name="student_feedback_message",),
    path("staff/view/feedback/", hod_views.staff_feedback_message,
         name="staff_feedback_message",),
    path("student/view/leave/", hod_views.view_student_leave,
         name="view_student_leave",),
    path("staff/view/leave/", hod_views.view_staff_leave, name="view_staff_leave",),
    path("attendance/view/", hod_views.admin_view_attendance,
         name="admin_view_attendance",),
    path("attendance/fetch/", hod_views.get_admin_attendance,
         name='get_admin_attendance'),
    path("student/add/", hod_views.add_student, name='add_student'),
    path(
        "student/enroll-existing/",
        hod_views.admin_enroll_existing_student,
        name="admin_enroll_existing_student",
    ),
    path("subject/add/", hod_views.add_subject, name='add_subject'),
    path("staff/manage/", hod_views.manage_staff, name='manage_staff'),
    path("student/manage/", hod_views.manage_student, name='manage_student'),
    path(
        "admin/students/by-course/",
        hod_views.admin_students_overview_by_course,
        name="admin_students_by_course",
    ),
    path(
        "admin/assessments/",
        hod_views.admin_assessments,
        name="admin_assessments",
    ),
    path("course/manage/", hod_views.manage_course, name='manage_course'),
    path("subject/manage/", hod_views.manage_subject, name='manage_subject'),
    path("staff/edit/<int:staff_id>", hod_views.edit_staff, name='edit_staff'),
    path("staff/delete/<int:staff_id>",
         hod_views.delete_staff, name='delete_staff'),

    path("course/delete/<int:course_id>",
         hod_views.delete_course, name='delete_course'),

    path("subject/delete/<int:subject_id>",
         hod_views.delete_subject, name='delete_subject'),

    path("session/delete/<int:session_id>",
         hod_views.delete_session, name='delete_session'),

    path("student/delete/<int:student_id>",
         hod_views.delete_student, name='delete_student'),
    path("student/edit/<int:student_id>",
         hod_views.edit_student, name='edit_student'),
    path("enrollment/<int:enrollment_id>/fee/",
         hod_views.edit_enrollment_fee, name='edit_enrollment_fee'),
    path("course/edit/<int:course_id>",
         hod_views.edit_course, name='edit_course'),
    path("subject/edit/<int:subject_id>",
         hod_views.edit_subject, name='edit_subject'),


    # Staff
    path("staff/home/", staff_views.staff_home, name='staff_home'),
    path(
        "staff/course/students/",
        staff_views.staff_course_students,
        name="staff_course_students",
    ),
    path(
        "staff/students/by-course/",
        staff_views.staff_students_overview_by_course,
        name="staff_students_by_course",
    ),
    path(
        "staff/finance/reports/",
        staff_views.staff_finance_reports,
        name="staff_finance_reports",
    ),
    path(
        "staff/finance/payment/",
        staff_views.staff_record_payment,
        name="staff_record_payment",
    ),
    path("staff/apply/leave/", staff_views.staff_apply_leave,
         name='staff_apply_leave'),
    path("staff/feedback/", staff_views.staff_feedback, name='staff_feedback'),
    path("staff/view/profile/", staff_views.staff_view_profile,
         name='staff_view_profile'),
    path("staff/classes/", staff_views.staff_my_classes, name='staff_my_classes'),
    path("staff/attendance/take/", staff_views.staff_take_attendance,
         name='staff_take_attendance'),
    path("staff/attendance/update/", staff_views.staff_update_attendance,
         name='staff_update_attendance'),
    path("staff/get_students/", staff_views.get_students, name='get_students'),
    path("staff/attendance/fetch/", staff_views.get_student_attendance,
         name='get_student_attendance'),
    path("staff/attendance/save/",
         staff_views.save_attendance, name='save_attendance'),
    path("staff/attendance/update/",
         staff_views.update_attendance, name='update_attendance'),
    path("staff/fcmtoken/", staff_views.staff_fcmtoken, name='staff_fcmtoken'),
    path("staff/view/notification/", staff_views.staff_view_notification,
         name="staff_view_notification"),
    path("staff/result/add/", staff_views.staff_add_result, name='staff_add_result'),
    path("staff/result/edit/", EditResultView.as_view(),
         name='edit_student_result'),
    path('staff/result/fetch/', staff_views.fetch_student_result,
         name='fetch_student_result'),

    # Instructor assessments
    path(
        "staff/assessments/",
        assessment_views.instructor_assessment_list,
        name="staff_assessment_list",
    ),
    path(
        "staff/assessments/add/",
        assessment_views.instructor_assessment_create,
        name="staff_assessment_create",
    ),
    path(
        "staff/assessments/<int:pk>/",
        assessment_views.instructor_assessment_detail,
        name="staff_assessment_detail",
    ),
    path(
        "staff/assessments/<int:pk>/submissions/",
        assessment_views.instructor_assessment_submissions,
        name="staff_assessment_submissions",
    ),
    path(
        "staff/assessments/<int:pk>/submissions/<int:sub_id>/grade/",
        assessment_views.instructor_grade_submission,
        name="staff_assessment_grade",
    ),

    # Admission Officer
    path("admission/student/add/", staff_views.admission_add_student, name="admission_add_student"),
    path(
        "admission/student/enroll-existing/",
        staff_views.admission_enroll_existing_student,
        name="admission_enroll_existing_student",
    ),



    # Student
    path("student/home/", student_views.student_home, name='student_home'),
    path("student/view/attendance/", student_views.student_view_attendance,
         name='student_view_attendance'),
    path("student/apply/leave/", student_views.student_apply_leave,
         name='student_apply_leave'),
    path("student/feedback/", student_views.student_feedback,
         name='student_feedback'),
    path("student/view/profile/", student_views.student_view_profile,
         name='student_view_profile'),
    path("student/fcmtoken/", student_views.student_fcmtoken,
         name='student_fcmtoken'),
    path("student/view/notification/", student_views.student_view_notification,
         name="student_view_notification"),
    path('student/view/result/', student_views.student_view_result,
         name='student_view_result'),
    path(
        "student/assessments/",
        student_views.student_assessment_list,
        name="student_assessment_list",
    ),
    path(
        "student/assessments/<int:pk>/",
        student_views.student_assessment_detail,
        name="student_assessment_detail",
    ),

    # Fees — receipts & statements (billing_views)
    path(
        "receipt/payment/<int:payment_id>/",
        billing_views.payment_receipt,
        name="payment_receipt",
    ),
    path(
        "fees/student/<int:student_id>/",
        billing_views.student_fee_statement,
        name="student_fee_statement",
    ),
    path(
        "fees/my/",
        billing_views.my_fee_statement,
        name="student_my_fee_statement",
    ),

]
