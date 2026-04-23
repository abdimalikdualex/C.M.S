from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.decorators.csrf import csrf_exempt

from .models import Attendance, Session, Staff, Student, Subject
from .roles import get_post_login_redirect_url


def login_page(request):
    if request.user.is_authenticated:
        return redirect(get_post_login_redirect_url(request.user))
    return render(request, 'main_app/login.html')


def doLogin(request, **kwargs):
    if request.method != 'POST':
        return HttpResponse("<h4>Denied</h4>")
    else:
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            return redirect(get_post_login_redirect_url(user))
        else:
            messages.error(request, "Invalid details")
            return redirect("/")


def logout_user(request):
    if request.user is not None:
        logout(request)
    return redirect("/")


@csrf_exempt
def get_attendance(request):
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    try:
        subject = get_object_or_404(Subject, id=subject_id)
        session = get_object_or_404(Session, id=session_id)
        attendance = Attendance.objects.filter(subject=subject, session=session)

        attendance_list = []
        for attd in attendance:
            data = {
                "id": attd.id,
                "attendance_date": str(attd.date),
                "session": attd.session.id
            }
            attendance_list.append(data)

        return JsonResponse(attendance_list, safe=False)
    except Exception:
        return JsonResponse([], safe=False)


def showFirebaseJS(request):
    data = """
    importScripts('https://www.gstatic.com/firebasejs/7.22.1/firebase-app.js');
    importScripts('https://www.gstatic.com/firebasejs/7.22.1/firebase-messaging.js');

    firebase.initializeApp({
        apiKey: "AIzaSyBarDWWHTfTMSrtc5Lj3Cdw5dEvjAkFwtM",
        authDomain: "sms-with-django.firebaseapp.com",
        databaseURL: "https://sms-with-django.firebaseio.com",
        projectId: "sms-with-django",
        storageBucket: "sms-with-django.appspot.com",
        messagingSenderId: "945324593139",
        appId: "1:945324593139:web:03fa99a8854bbd38420c86",
        measurementId: "G-2F2RXTL9GT"
    });

    const messaging = firebase.messaging();
    messaging.setBackgroundMessageHandler(function (payload) {
        const notification = JSON.parse(payload);
        const notificationOption = {
            body: notification.body,
            icon: notification.icon
        }
        return self.registration.showNotification(payload.notification.title, notificationOption);
    });
    """
    return HttpResponse(data, content_type='application/javascript')


def active_sessions(request):
    if not request.user.is_authenticated:
        return redirect(reverse("login_page"))

    ut = str(getattr(request.user, "user_type", "") or "").strip()
    sessions = Session.objects.active()

    if ut == "3":
        try:
            student = Student.objects.select_related("session").get(admin=request.user)
            if student.session_id:
                sessions = Session.objects.filter(id=student.session_id)
            elif not sessions.exists():
                sessions = Session.objects.latest_first()[:1]
        except Student.DoesNotExist:
            if not sessions.exists():
                sessions = Session.objects.latest_first()[:1]

    elif ut == "2":
        try:
            staff = Staff.objects.get(admin=request.user)
            if staff.role == "instructor":
                course_ids = Subject.objects.filter(staff=staff).values_list("course_id", flat=True)
                scoped = Session.objects.filter(
                    enrollments__course_id__in=course_ids
                ).distinct().latest_first()
                sessions = scoped if scoped.exists() else sessions
        except Staff.DoesNotExist:
            pass

        if not sessions.exists():
            sessions = Session.objects.latest_first()[:1]

    else:
        if not sessions.exists():
            sessions = Session.objects.latest_first()[:1]

    return render(
        request,
        "main_app/active_sessions.html",
        {
            "page_title": "Active Sessions",
            "sessions": sessions,
        },
    )