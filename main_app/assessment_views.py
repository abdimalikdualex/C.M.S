"""
Instructor assessments (homework / exercises): create, list submissions, grade.
"""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import AssessmentForm, SubmissionGradeForm
from .models import Assessment, Enrollment, Staff, Student, Submission


def _require_instructor(request):
    staff = get_object_or_404(Staff, admin=request.user)
    if staff.role != "instructor":
        messages.error(request, "Only instructors can manage assessments.")
        return None
    return staff


def _students_for_course(course):
    ids = set(
        Enrollment.objects.filter(course=course, status="active").values_list(
            "student_id", flat=True
        )
    )
    ids.update(Student.objects.filter(course=course).values_list("id", flat=True))
    return Student.objects.filter(pk__in=ids).select_related("admin").order_by(
        "admin__full_name", "admin__first_name", "student_id"
    )


def instructor_assessment_list(request):
    staff = _require_instructor(request)
    if staff is None:
        return redirect(reverse("staff_home"))
    qs = Assessment.objects.filter(instructor=staff).select_related("course", "session")
    assessments = qs.annotate(sub_cnt=Count("submissions")).order_by("-due_date")
    context = {
        "page_title": "Assessments",
        "assessments": assessments,
        "staff": staff,
    }
    return render(request, "staff_template/assessment_list.html", context)


def instructor_assessment_create(request):
    staff = _require_instructor(request)
    if staff is None:
        return redirect(reverse("staff_home"))
    if not staff.course_id:
        messages.error(request, "You have no course assigned. Ask the administrator to assign a course.")
        return redirect(reverse("staff_assessment_list"))
    form = AssessmentForm(request.POST or None, request.FILES or None, staff=staff)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.instructor = staff
        obj.save()
        messages.success(request, "Assessment created.")
        return redirect(reverse("staff_assessment_submissions", kwargs={"pk": obj.pk}))
    return render(
        request,
        "staff_template/assessment_form.html",
        {"page_title": "Create assessment", "form": form, "staff": staff},
    )


def instructor_assessment_detail(request, pk):
    staff = _require_instructor(request)
    if staff is None:
        return redirect(reverse("staff_home"))
    assessment = get_object_or_404(Assessment, pk=pk, instructor=staff)
    form = AssessmentForm(
        request.POST or None,
        request.FILES or None,
        instance=assessment,
        staff=staff,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Assessment updated.")
        return redirect(reverse("staff_assessment_detail", kwargs={"pk": pk}))
    return render(
        request,
        "staff_template/assessment_form.html",
        {
            "page_title": f"Edit: {assessment.title}",
            "form": form,
            "staff": staff,
            "assessment": assessment,
        },
    )


def instructor_assessment_submissions(request, pk):
    staff = _require_instructor(request)
    if staff is None:
        return redirect(reverse("staff_home"))
    assessment = get_object_or_404(Assessment, pk=pk, instructor=staff)
    students = _students_for_course(assessment.course)
    subs = {
        s.student_id: s
        for s in assessment.submissions.select_related("student__admin").all()
    }
    rows = []
    for st in students:
        rows.append({"student": st, "submission": subs.get(st.pk)})
    now = timezone.now()
    context = {
        "page_title": f"Submissions — {assessment.title}",
        "assessment": assessment,
        "rows": rows,
        "now": now,
    }
    return render(request, "staff_template/assessment_submissions.html", context)


def instructor_grade_submission(request, pk, sub_id):
    staff = _require_instructor(request)
    if staff is None:
        return redirect(reverse("staff_home"))
    assessment = get_object_or_404(Assessment, pk=pk, instructor=staff)
    submission = get_object_or_404(Submission, pk=sub_id, assessment=assessment)
    grade_initial = {}
    if submission.grade is not None:
        grade_initial["grade"] = submission.grade
    grade_initial["feedback"] = submission.feedback or ""
    form = SubmissionGradeForm(request.POST or None, initial=grade_initial)
    if request.method == "POST" and form.is_valid():
        submission.grade = form.cleaned_data["grade"]
        submission.feedback = form.cleaned_data.get("feedback") or ""
        submission.save(update_fields=["grade", "feedback", "updated_at"])
        messages.success(request, "Grade saved.")
        return redirect(reverse("staff_assessment_submissions", kwargs={"pk": pk}))
    return render(
        request,
        "staff_template/assessment_grade.html",
        {
            "page_title": "Grade submission",
            "assessment": assessment,
            "submission": submission,
            "form": form,
        },
    )
