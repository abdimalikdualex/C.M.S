"""Student-facing ICT hub: growth dashboard, events, completion certificates."""
import math
import re

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import StudentHubProfileForm
from .pdf_certificate import build_completion_certificate_pdf
from .models import (
    Assessment,
    AttendanceReport,
    Enrollment,
    HubEvent,
    HubEventRegistration,
    Student,
    StudentHubProfile,
)


def _student(request):
    return get_object_or_404(Student, admin=request.user)


def _student_enrolled_course_ids(student):
    ids = set()
    if student.course_id:
        ids.add(student.course_id)
    ids.update(
        student.enrollments.filter(status="active").values_list("course_id", flat=True)
    )
    return ids


def student_growth_hub(request):
    student = _student(request)
    profile, _ = StudentHubProfile.objects.get_or_create(student=student)
    hub_form = StudentHubProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=profile,
        prefix="hub",
    )
    if request.method == "POST" and request.POST.get("action") == "save_hub_profile":
        if hub_form.is_valid():
            hub_form.save()
            messages.success(
                request, "Your digital profile and portfolio links were saved."
            )
            return redirect(reverse("student_growth_hub"))
        messages.error(request, "Please fix the errors in your profile form.")

    enrollments = list(
        student.enrollments.select_related("course", "session").order_by("-created_at")
    )
    cids = _student_enrolled_course_ids(student)

    total_att = AttendanceReport.objects.filter(student=student).count()
    present = AttendanceReport.objects.filter(student=student, status=True).count()
    attendance_pct = int(math.floor((present / total_att) * 100)) if total_att else 0

    assess_totals = {cid: 0 for cid in cids}
    assess_done = {cid: 0 for cid in cids}
    for cid in cids:
        tc = Assessment.objects.filter(course_id=cid).count()
        assess_totals[cid] = tc
        subbed = (
            Assessment.objects.filter(course_id=cid, submissions__student=student)
            .distinct()
            .count()
        )
        assess_done[cid] = subbed

    enrollment_rows = []
    practical_pct_sum = 0
    practical_n = 0
    for e in enrollments:
        t = assess_totals.get(e.course_id, 0)
        d = assess_done.get(e.course_id, 0)
        pct = int(round((d / t) * 100)) if t else 0
        notes = list(
            e.mentor_notes.select_related("author__admin").order_by("-created_at")[:5]
        )
        enrollment_rows.append(
            {
                "enrollment": e,
                "practical_total": t,
                "practical_done": d,
                "practical_pct": pct,
                "mentor_notes": notes,
            }
        )
        if t > 0:
            practical_pct_sum += pct
            practical_n += 1

    overall_practical_pct = (
        int(round(practical_pct_sum / practical_n)) if practical_n else 0
    )

    completed = [e for e in enrollments if e.status == "completed"]
    badges = [b.strip() for b in (profile.skill_badges or "").split(",") if b.strip()]

    upcoming = (
        HubEvent.objects.filter(is_published=True, starts_at__gte=timezone.now())
        .order_by("starts_at")[:6]
    )
    reg_event_ids = set(
        HubEventRegistration.objects.filter(student=student).values_list(
            "event_id", flat=True
        )
    )

    completion_approx = int(round((attendance_pct + overall_practical_pct) / 2))

    return render(
        request,
        "student_template/student_growth_hub.html",
        {
            "page_title": "Growth hub",
            "hub_form": hub_form,
            "enrollment_rows": enrollment_rows,
            "attendance_pct": attendance_pct,
            "overall_practical_pct": overall_practical_pct,
            "completion_approx": completion_approx,
            "completed_enrollments": completed,
            "skill_badges_list": badges,
            "upcoming_events": upcoming,
            "registered_event_ids": reg_event_ids,
        },
    )


def student_hub_events(request):
    student = _student(request)
    events = HubEvent.objects.filter(is_published=True).order_by("starts_at")
    reg_ids = set(
        HubEventRegistration.objects.filter(student=student).values_list(
            "event_id", flat=True
        )
    )

    if request.method == "POST":
        eid = request.POST.get("event_id")
        event = get_object_or_404(HubEvent, pk=eid, is_published=True)
        if event.max_attendees:
            cnt = HubEventRegistration.objects.filter(event=event).count()
            if cnt >= event.max_attendees:
                messages.error(request, "This event has reached its capacity.")
                return redirect(reverse("student_hub_events"))
        _, created = HubEventRegistration.objects.get_or_create(
            event=event, student=student
        )
        if created:
            messages.success(request, f"You are registered for {event.title}.")
        else:
            messages.info(request, "You are already registered for this event.")
        return redirect(reverse("student_hub_events"))

    rows = []
    now = timezone.now()
    for ev in events:
        reg_count = HubEventRegistration.objects.filter(event=ev).count()
        rows.append(
            {
                "event": ev,
                "registered": ev.id in reg_ids,
                "full": bool(ev.max_attendees and reg_count >= ev.max_attendees),
                "past": ev.starts_at < now,
            }
        )

    return render(
        request,
        "student_template/student_hub_events.html",
        {"page_title": "Hub events & workshops", "rows": rows},
    )


def student_certificate(request, enrollment_id):
    student = _student(request)
    enr = get_object_or_404(
        Enrollment.objects.select_related("course", "session", "student__admin"),
        pk=enrollment_id,
        student=student,
        status="completed",
    )
    return render(
        request,
        "student_template/student_certificate.html",
        {
            "page_title": f"Certificate — {enr.course.name}",
            "enrollment": enr,
        },
    )


def student_certificate_pdf(request, enrollment_id):
    student = _student(request)
    enr = get_object_or_404(
        Enrollment.objects.select_related("course", "session", "student__admin"),
        pk=enrollment_id,
        student=student,
        status="completed",
    )
    pdf_bytes = build_completion_certificate_pdf(
        enr,
        college_name=getattr(settings, "COLLEGE_NAME", "ELEVATE DIGITAL HUB"),
        hub_tagline=getattr(settings, "HUB_TAGLINE", "ICT Hub System"),
        college_location=getattr(settings, "COLLEGE_LOCATION", ""),
    )
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (enr.course.name or "course")[:48]).strip("-").lower() or "course"
    sid = (enr.student.student_id or str(enr.student.pk)).replace("/", "-")
    resp["Content-Disposition"] = f'attachment; filename="certificate-{sid}-{slug}.pdf"'
    return resp
