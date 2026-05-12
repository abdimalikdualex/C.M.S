from django.shortcuts import get_object_or_404, render, redirect
from django.views import View
from django.contrib import messages
from .models import Subject, Staff, Student, StudentResult
from .forms import EditResultForm
from django.urls import reverse


class EditResultView(View):
    def get(self, request, *args, **kwargs):
        staff = get_object_or_404(Staff, admin=request.user)
        resultForm = EditResultForm(staff=staff)
        context = {
            'form': resultForm,
            'page_title': "Edit Student's Result"
        }
        return render(request, "staff_template/edit_student_result.html", context)

    def post(self, request, *args, **kwargs):
        staff = get_object_or_404(Staff, admin=request.user)
        form = EditResultForm(request.POST, staff=staff)
        context = {'form': form, 'page_title': "Edit Student's Result"}
        if form.is_valid():
            try:
                student = form.cleaned_data.get('student')
                subject = form.cleaned_data.get('subject')
                test = form.cleaned_data.get('test')
                exam = form.cleaned_data.get('exam')
                remarks = (form.cleaned_data.get('remarks') or "").strip()
                sess = form.cleaned_data.get('session')
                result, created = StudentResult.objects.get_or_create(
                    student=student,
                    subject=subject,
                    defaults={
                        "test": test,
                        "exam": exam,
                        "remarks": remarks,
                        "session": sess,
                        "entered_by": request.user,
                    },
                )
                if not created:
                    result.exam = exam
                    result.test = test
                    result.remarks = remarks
                    result.session = sess
                    result.entered_by = request.user
                    result.save()
                messages.success(request, "Result Updated")
                return redirect(reverse('edit_student_result'))
            except Exception:
                messages.warning(request, "Result Could Not Be Updated")
        else:
            messages.warning(request, "Result Could Not Be Updated")
        return render(request, "staff_template/edit_student_result.html", context)
