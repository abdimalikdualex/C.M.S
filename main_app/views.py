import json
import requests
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.decorators.csrf import csrf_exempt

from .EmailBackend import EmailBackend
from .models import Attendance, Session, Staff, Student, Subject
from .roles import get_post_login_redirect_url

# Create your views here.


def login_page(request):
    if request.user.is_authenticated:
        return redirect(get_post_login_redirect_url(request.user))
    return render(request, 'main_app/login.html')


def doLogin(request, **kwargs):
    if request.method != 'POST':
        return HttpResponse("<h4>Denied</h4>")
    else:
        #Google recaptcha
        captcha_token = request.POST.get('g-recaptcha-response')
        captcha_url = "https://www.google.com/recaptcha/api/siteverify"
        captcha_key = "6LfswtgZAAAAABX9gbLqe-d97qE2g1JP8oUYritJ"
        data = {
            'secret': captcha_key,
            'response': captcha_token
        }
        # Make request
        try:
            captcha_server = requests.post(url=captcha_url, data=data)
            response = json.loads(captcha_server.text)
            if response['success'] == False:
                messages.error(request, 'Invalid Captcha. Try Again')
                return redirect('/')
        except:
            messages.error(request, 'Captcha could not be verified. Try Again')
            return redirect('/')
        
        #Authenticate
        user = EmailBackend.authenticate(request, username=request.POST.get('email'), password=request.POST.get('password'))
        if user != None:
            login(request, user)
            return redirect(get_post_login_redirect_url(user))
        else:
            messages.error(request, "Invalid details")
            return redirect("/")



def logout_user(request):
    if request.user != None:
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
        return JsonResponse(json.dumps(attendance_list), safe=False)
    except Exception as e:
        return None


def showFirebaseJS(request):
    data = """
    // Give the service worker access to Firebase Messaging.
// Note that you can only use Firebase Messaging here, other Firebase libraries
// are not available in the service worker.
importScripts('https://www.gstatic.com/firebasejs/7.22.1/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/7.22.1/firebase-messaging.js');

// Initialize the Firebase app in the service worker by passing in
// your app's Firebase config object.
// https://firebase.google.com/docs/web/setup#config-object
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

// Retrieve an instance of Firebase Messaging so that it can handle background
// messages.
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
    """Role-aware active session list opened from sidebar."""
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
                scoped = Session.objects.filter(enrollments__course_id__in=course_ids).distinct().latest_first()
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
