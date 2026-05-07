from django import forms
from django.forms.widgets import DateInput, TextInput

from .models import *
from .money import format_money, quantize_kes
from django.utils import timezone
from django.utils.crypto import get_random_string
import re
import uuid


class FormSettings(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormSettings, self).__init__(*args, **kwargs)
        # Here make some changes such as:
        for field in self.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'


class CustomUserForm(FormSettings):
    phone_number = forms.CharField(required=True, label="Phone number")
    email = forms.EmailField(required=False)
    gender = forms.ChoiceField(choices=[('M', 'Male'), ('F', 'Female')])
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    address = forms.CharField(widget=forms.Textarea)
    password = forms.CharField(widget=forms.PasswordInput)
    widget = {
        'password': forms.PasswordInput(),
    }
    profile_pic = forms.ImageField()

    def __init__(self, *args, **kwargs):
        super(CustomUserForm, self).__init__(*args, **kwargs)

        if kwargs.get('instance'):
            instance = kwargs.get('instance').admin.__dict__
            self.fields['password'].required = False
            for field in CustomUserForm.Meta.fields:
                self.fields[field].initial = instance.get(field)
            u = kwargs.get("instance").admin
            fn = (getattr(u, "first_name", None) or "").strip()
            ln = (getattr(u, "last_name", None) or "").strip()
            full = (getattr(u, "full_name", None) or "").strip()
            if full and not fn and not ln:
                self.fields["first_name"].initial = full
                self.fields["last_name"].initial = ""
            if self.instance.pk is not None:
                self.fields['password'].widget.attrs['placeholder'] = "Fill this only if you wish to update password"

    def clean_email(self, *args, **kwargs):
        formEmail = (self.cleaned_data.get('email') or "").strip().lower()
        # Allow blank email: we'll auto-generate later from phone number (Kenyan walk-in flow)
        if not formEmail:
            return formEmail
        if self.instance.pk is None:  # Insert
            if CustomUser.objects.filter(email=formEmail).exists():
                raise forms.ValidationError(
                    "The given email is already registered")
        else:  # Update
            dbEmail = self.Meta.model.objects.get(
                id=self.instance.pk).admin.email.lower()
            if dbEmail != formEmail:  # There has been changes
                if CustomUser.objects.filter(email=formEmail).exists():
                    raise forms.ValidationError("The given email is already registered")

        return formEmail

    def clean_phone_number(self, *args, **kwargs):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        phone = re.sub(r"\s+", "", phone)
        if not phone:
            raise forms.ValidationError("Phone number is required")
        # Basic Kenyan-friendly normalization (kept simple for MVP)
        if phone.startswith("0") and len(phone) >= 10:
            phone = "254" + phone[1:]
        if self.instance.pk is None:
            if CustomUser.objects.filter(phone_number=phone).exists():
                raise forms.ValidationError("This phone number is already registered")
        return phone

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'phone_number', 'email', 'gender',  'password','profile_pic', 'address' ]


def walk_in_student_user_defaults(cleaned_data):
    """
    Build user fields for quick student registration when only course is required.
    Does not include course/session — those come from cleaned_data separately.
    """
    first_name = (cleaned_data.get("first_name") or "").strip() or "Student"
    last_name = (cleaned_data.get("last_name") or "").strip() or "-"
    raw_phone = (cleaned_data.get("phone_number") or "").strip()
    phone_number = re.sub(r"\s+", "", raw_phone)
    if phone_number.startswith("0") and len(phone_number) >= 10:
        phone_number = "254" + phone_number[1:]
    if not phone_number:
        for _ in range(8):
            cand = f"254W{uuid.uuid4().hex[:12].upper()}"
            if len(cand) <= 20 and not CustomUser.objects.filter(phone_number=cand).exists():
                phone_number = cand
                break
        else:
            phone_number = f"254W{uuid.uuid4().hex[:12].upper()}"
    email = (cleaned_data.get("email") or "").strip().lower()
    if not email:
        for _ in range(8):
            cand = f"walkin-{uuid.uuid4().hex[:18]}@walkin.local"
            if not CustomUser.objects.filter(email=cand).exists():
                email = cand
                break
        else:
            email = f"walkin-{uuid.uuid4().hex}@walkin.local"
    password = (cleaned_data.get("password") or "").strip()
    if not password:
        password = get_random_string(14)
    gender = cleaned_data.get("gender") or "M"
    if gender not in ("M", "F"):
        gender = "M"
    address = (cleaned_data.get("address") or "").strip() or "—"
    return {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "email": email,
        "password": password,
        "gender": gender,
        "address": address,
    }


class StudentForm(CustomUserForm):
    # Optional quick-payment fields (Kenyan walk-in flow)
    pay_amount = forms.IntegerField(
        required=False,
        min_value=0,
        label="Initial payment amount",
        error_messages={"invalid": "Only whole numbers are allowed. Decimals are not permitted."},
    )
    pay_mode = forms.ChoiceField(required=False, choices=Payment.MODE, label="Payment mode")
    pay_reference = forms.CharField(required=False, label="Payment reference (M-Pesa code)")
    pay_note = forms.CharField(required=False, label="Payment note")
    enrollment_date = forms.DateField(
        required=False,
        label="Start date",
        widget=DateInput(attrs={"type": "date"}),
        help_text="Defaults to today if left blank.",
    )
    agreed_total_fee = forms.IntegerField(
        required=False,
        min_value=0,
        label="Agreed total fee (KES)",
        help_text="Defaults to the course fee. Override only if a different fee was agreed (scholarship, sibling discount, etc.).",
        error_messages={"invalid": "Only whole numbers are allowed. Decimals are not permitted."},
    )

    def __init__(self, *args, **kwargs):
        super(StudentForm, self).__init__(*args, **kwargs)
        is_new_student = not getattr(self.instance, "pk", None)
        # Walk-in add student: only course is required; other user fields optional.
        self.fields["email"].required = False
        self.fields["address"].required = False
        self.fields["gender"].required = False
        self.fields["last_name"].required = False
        self.fields["profile_pic"].required = False
        self.fields["session"].required = True
        self.fields["session"].queryset = Session.objects.latest_first()
        self.fields["session"].empty_label = "Select intake/session"
        self.fields["enrollment_date"].initial = timezone.now().date()
        if is_new_student:
            self.fields["course"].required = True
            self.fields["first_name"].required = False
            self.fields["phone_number"].required = False
            self.fields["password"].required = False
            self.fields["course"].help_text = "Required — select the course for this learner."
            active_session = Session.objects.active().first()
            if active_session:
                self.fields["session"].initial = active_session.pk
        else:
            self.fields["course"].required = True
            self.fields["first_name"].required = True
            self.fields["phone_number"].required = True
            self.fields["password"].required = False
        # Show fee right inside course dropdown for faster desk decisions.
        course_field = self.fields.get("course")
        if course_field is not None:
            choices = [("", "---------")]
            for c in course_field.queryset.order_by("name"):
                total_fee = c.total_fee_for_student()
                level_suffix = f" ({c.get_level_display()})" if getattr(c, "level", "") else ""
                choices.append((c.pk, f"{c.name}{level_suffix} — KES {format_money(total_fee)}"))
            course_field.choices = choices

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        phone = re.sub(r"\s+", "", phone)
        if not phone:
            return ""
        if phone.startswith("0") and len(phone) >= 10:
            phone = "254" + phone[1:]
        if getattr(self.instance, "pk", None):
            admin_id = self.instance.admin_id
            if CustomUser.objects.filter(phone_number=phone).exclude(pk=admin_id).exists():
                raise forms.ValidationError("This phone number is already registered")
        else:
            if CustomUser.objects.filter(phone_number=phone).exists():
                raise forms.ValidationError("This phone number is already registered")
        return phone

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        if not getattr(self.instance, "pk", None) and not cleaned.get("course"):
            self.add_error("course", "Please select a course.")
        if not cleaned.get("session"):
            self.add_error("session", "Please select an intake/session.")
        course = cleaned.get("course")
        amount = int(cleaned.get("pay_amount") or 0)
        mode = cleaned.get("pay_mode") or "cash"
        reference = (cleaned.get("pay_reference") or "").strip()
        if amount and mode == "mpesa" and not reference:
            self.add_error("pay_reference", "M-Pesa reference is required for mobile money payments.")
        agreed = cleaned.get("agreed_total_fee")
        course_default_fee = int(course.total_fee_for_student() or 0) if course else 0
        effective_total_fee = int(agreed) if agreed not in (None, "") else course_default_fee
        cleaned["effective_total_fee"] = effective_total_fee
        if amount and effective_total_fee and amount > effective_total_fee:
            self.add_error(
                "pay_amount",
                "Initial payment cannot exceed the agreed total fee.",
            )
        return cleaned

    class Meta(CustomUserForm.Meta):
        model = Student
        fields = CustomUserForm.Meta.fields + \
            ['course', 'session', 'enrollment_date']


class AdminForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        super(AdminForm, self).__init__(*args, **kwargs)

    class Meta(CustomUserForm.Meta):
        model = Admin
        fields = CustomUserForm.Meta.fields


class StaffForm(CustomUserForm):
    """
    ICT Hub edition: the only role that can be created here is Instructor.
    The legacy admission/finance choices are intentionally hidden so the
    superadmin owns admissions and fee tracking, and the instructor pool
    stays clean.
    """

    role = forms.ChoiceField(
        choices=(("instructor", "Instructor"),),
        initial="instructor",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        super(StaffForm, self).__init__(*args, **kwargs)
        self.fields["course"].required = True
        self.fields["course"].empty_label = "Select course (teaching assignment)"

    def clean(self):
        cleaned = super(StaffForm, self).clean()
        cleaned["role"] = "instructor"
        if not cleaned.get("course"):
            raise forms.ValidationError("Instructors must be assigned to a course.")
        return cleaned

    class Meta(CustomUserForm.Meta):
        model = Staff
        fields = CustomUserForm.Meta.fields + ["role", "course"]


class CourseForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(CourseForm, self).__init__(*args, **kwargs)
        for key in ("monthly_fee", "full_fee"):
            if key in self.fields:
                self.fields[key].error_messages["invalid"] = "Only whole numbers are allowed. Decimals are not permitted."

    class Meta:
        fields = [
            'name',
            'duration_value',
            'duration_unit',
            'payment_plan',
            'monthly_fee',
            'full_fee',
            'level',
            'rolling_intake',
            'intake_start',
            'intake_end',
        ]
        model = Course


class PaymentForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(PaymentForm, self).__init__(*args, **kwargs)
        if "amount" in self.fields:
            self.fields["amount"].error_messages["invalid"] = "Only whole numbers are allowed. Decimals are not permitted."

    class Meta:
        model = Payment
        fields = ["amount", "mode", "reference", "note"]


class RecordPaymentForm(forms.Form):
    """Walk-in / finance desk: identify student by official ID or phone, then record fee."""

    lookup = forms.CharField(
        required=True,
        label="Student ID or phone",
        help_text="Use STU-… student ID or the phone number on file.",
    )
    course = forms.ModelChoiceField(
        required=False,
        queryset=Course.objects.all().order_by("name"),
        label="Course (optional)",
        help_text="Choose course if student has multiple active enrollments.",
    )
    amount = forms.IntegerField(
        required=True,
        min_value=0,
        label="Amount (KES)",
        error_messages={"invalid": "Only whole numbers are allowed. Decimals are not permitted."},
    )
    mode = forms.ChoiceField(choices=Payment.MODE, label="Payment mode")
    reference = forms.CharField(
        required=False,
        label="Reference (e.g. M-Pesa code)",
    )
    note = forms.CharField(required=False, label="Note")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.visible_fields():
            f.field.widget.attrs.setdefault("class", "form-control")

    def clean_lookup(self):
        raw = (self.cleaned_data.get("lookup") or "").strip()
        if not raw:
            raise forms.ValidationError("Enter student ID or phone number.")
        return raw

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        raw = cleaned.get("lookup")
        phone = re.sub(r"\s+", "", raw)
        if phone.startswith("0") and len(phone) >= 10:
            phone = "254" + phone[1:]
        student = None
        if raw.upper().startswith("STU-"):
            student = Student.objects.filter(student_id__iexact=raw.strip()).select_related("admin").first()
        if student is None:
            student = Student.objects.filter(admin__phone_number=phone).select_related("admin").first()
        if student is None:
            student = Student.objects.filter(admin__phone_number__icontains=raw.strip()).first()
        if student is None:
            raise forms.ValidationError("No student found for that ID or phone.")
        cleaned["student"] = student
        picked_course = cleaned.get("course")
        enrollment_qs = Enrollment.objects.filter(student=student, status="active").select_related("course")
        if picked_course:
            enrollment = enrollment_qs.filter(course=picked_course).first()
            if enrollment is None:
                raise forms.ValidationError("Selected course is not an active enrollment for this student.")
        else:
            enrollment = enrollment_qs.order_by("-start_date", "-id").first()
        if enrollment is None:
            raise forms.ValidationError("No active enrollment found. Enroll the student in a course first.")
        cleaned["enrollment"] = enrollment
        if cleaned.get("amount") and cleaned["amount"] > enrollment.balance_due:
            raise forms.ValidationError("Amount cannot exceed this course balance.")
        return cleaned


class EnrollExistingStudentForm(forms.Form):
    lookup = forms.CharField(required=True, label="Student ID or phone")
    course = forms.ModelChoiceField(required=True, queryset=Course.objects.all().order_by("name"))
    session = forms.ModelChoiceField(required=True, queryset=Session.objects.none(), label="Session / intake")
    start_date = forms.DateField(required=False, widget=DateInput(attrs={"type": "date"}))
    agreed_total_fee = forms.IntegerField(
        required=False,
        min_value=0,
        label="Agreed total fee (KES)",
        help_text="Defaults to the course fee. Override only if a different fee was agreed.",
        error_messages={"invalid": "Only whole numbers are allowed. Decimals are not permitted."},
    )
    pay_amount = forms.IntegerField(
        required=False,
        min_value=0,
        label="Initial payment",
        error_messages={"invalid": "Only whole numbers are allowed. Decimals are not permitted."},
    )
    pay_mode = forms.ChoiceField(required=False, choices=Payment.MODE, label="Payment mode")
    pay_reference = forms.CharField(required=False, label="Payment reference")
    pay_note = forms.CharField(required=False, label="Payment note")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].initial = timezone.now().date()
        self.fields["session"].queryset = Session.objects.latest_first()
        self.fields["session"].empty_label = "Select intake/session"
        active_session = Session.objects.active().first()
        if active_session:
            self.fields["session"].initial = active_session.pk
        for f in self.visible_fields():
            f.field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        raw = (cleaned.get("lookup") or "").strip()
        phone = re.sub(r"\s+", "", raw)
        if phone.startswith("0") and len(phone) >= 10:
            phone = "254" + phone[1:]
        student = None
        if raw.upper().startswith("STU-"):
            student = Student.objects.filter(student_id__iexact=raw).select_related("admin").first()
        if student is None:
            student = Student.objects.filter(admin__phone_number=phone).select_related("admin").first()
        if student is None:
            raise forms.ValidationError("No student found for that ID or phone.")
        course = cleaned.get("course")
        if Enrollment.objects.filter(student=student, course=course).exists():
            raise forms.ValidationError("Student is already enrolled in this course.")
        amt = int(cleaned.get("pay_amount") or 0)
        course_default_fee = int(course.total_fee_for_student() or 0)
        agreed = cleaned.get("agreed_total_fee")
        effective_total_fee = int(agreed) if agreed not in (None, "") else course_default_fee
        if amt and effective_total_fee and amt > effective_total_fee:
            raise forms.ValidationError("Initial payment cannot exceed the agreed total fee.")
        cleaned["student"] = student
        cleaned["total_fee"] = effective_total_fee
        return cleaned


class SubjectForm(FormSettings):

    def __init__(self, *args, **kwargs):
        super(SubjectForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Subject
        fields = ['name', 'staff', 'course']


class SessionForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(SessionForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Session
        fields = '__all__'
        widgets = {
            'start_year': DateInput(attrs={'type': 'date'}),
            'end_year': DateInput(attrs={'type': 'date'}),
        }


class LeaveReportStaffForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(LeaveReportStaffForm, self).__init__(*args, **kwargs)

    class Meta:
        model = LeaveReportStaff
        fields = ['date', 'message']
        widgets = {
            'date': DateInput(attrs={'type': 'date'}),
        }


class FeedbackStaffForm(FormSettings):

    def __init__(self, *args, **kwargs):
        super(FeedbackStaffForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeedbackStaff
        fields = ['feedback']


class LeaveReportStudentForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(LeaveReportStudentForm, self).__init__(*args, **kwargs)

    class Meta:
        model = LeaveReportStudent
        fields = ['date', 'message']
        widgets = {
            'date': DateInput(attrs={'type': 'date'}),
        }


class FeedbackStudentForm(FormSettings):

    def __init__(self, *args, **kwargs):
        super(FeedbackStudentForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeedbackStudent
        fields = ['feedback']


class StudentEditForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        super(StudentEditForm, self).__init__(*args, **kwargs)

    class Meta(CustomUserForm.Meta):
        model = Student
        fields = CustomUserForm.Meta.fields 


class StaffEditForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        super(StaffEditForm, self).__init__(*args, **kwargs)

    class Meta(CustomUserForm.Meta):
        model = Staff
        fields = CustomUserForm.Meta.fields


class EditResultForm(FormSettings):
    # IMPORTANT: keep queryset lazy at import time; DB tables may not exist during startup/deploy.
    session_list = Session.objects.none()
    session_year = forms.ModelChoiceField(
        label="Session Year", queryset=session_list, required=True)

    def __init__(self, *args, **kwargs):
        super(EditResultForm, self).__init__(*args, **kwargs)
        self.fields["session_year"].queryset = Session.objects.active_or_latest()
        latest_active = Session.objects.active_or_latest().first()
        if latest_active and not self.initial.get("session_year"):
            self.fields["session_year"].initial = latest_active.pk

    class Meta:
        model = StudentResult
        fields = ['session_year', 'subject', 'student', 'test', 'exam']


class AdmissionOfficerCreateForm(forms.Form):
    full_name = forms.CharField(required=True, label="Full name")
    phone_number = forms.CharField(required=True, label="Phone number")
    email = forms.EmailField(required=False, label="Email (optional)")
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    is_active = forms.BooleanField(required=False, initial=True, label="Active account")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.visible_fields():
            f.field.widget.attrs.setdefault("class", "form-control")

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        phone = re.sub(r"\s+", "", phone)
        if not phone:
            raise forms.ValidationError("Phone number is required")
        if phone.startswith("0") and len(phone) >= 10:
            phone = "254" + phone[1:]
        if CustomUser.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("This phone number is already registered")
        return phone

    def clean_email(self):
        em = (self.cleaned_data.get("email") or "").strip().lower()
        if not em:
            return em
        if CustomUser.objects.filter(email=em).exists():
            raise forms.ValidationError("This email is already registered")
        return em

    def clean_full_name(self):
        n = (self.cleaned_data.get("full_name") or "").strip()
        if not n:
            raise forms.ValidationError("Full name is required")
        return n


class AdmissionOfficerEditForm(forms.Form):
    full_name = forms.CharField(required=True, label="Full name")
    phone_number = forms.CharField(required=True, label="Phone number")
    email = forms.EmailField(required=False)
    password = forms.CharField(widget=forms.PasswordInput, required=False)
    is_active = forms.BooleanField(required=False, label="Active account")

    def __init__(self, *args, staff=None, **kwargs):
        self.staff = staff
        super().__init__(*args, **kwargs)
        for f in self.visible_fields():
            f.field.widget.attrs.setdefault("class", "form-control")
        if staff:
            u = staff.admin
            combined = (
                (u.first_name or "").strip()
                + (
                    (" " + (u.last_name or "").strip())
                    if (u.last_name or "").strip()
                    else ""
                )
            ).strip()
            self.fields["full_name"].initial = (getattr(u, "full_name", None) or "").strip() or combined
            self.fields["phone_number"].initial = u.phone_number
            self.fields["email"].initial = u.email
            self.fields["is_active"].initial = u.is_active
            self.fields["password"].widget.attrs.setdefault(
                "placeholder", "Leave blank to keep password"
            )

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        phone = re.sub(r"\s+", "", phone)
        if not phone:
            raise forms.ValidationError("Phone number is required")
        if phone.startswith("0") and len(phone) >= 10:
            phone = "254" + phone[1:]
        uid = self.staff.admin_id if self.staff else None
        qs = CustomUser.objects.filter(phone_number=phone)
        if uid:
            qs = qs.exclude(pk=uid)
        if qs.exists():
            raise forms.ValidationError("This phone number is already registered")
        return phone

    def clean_email(self):
        em = (self.cleaned_data.get("email") or "").strip().lower()
        if not em:
            return em
        uid = self.staff.admin_id if self.staff else None
        qs = CustomUser.objects.filter(email=em)
        if uid:
            qs = qs.exclude(pk=uid)
        if qs.exists():
            raise forms.ValidationError("This email is already registered")
        return em


class DirectorCreateForm(forms.Form):
    """
    Superadmin-only form to create a Manager / Director account.
    Mirrors AdmissionOfficerCreateForm but produces CustomUser.user_type='4'.
    """

    full_name = forms.CharField(required=True, label="Full name")
    phone_number = forms.CharField(required=True, label="Phone number")
    email = forms.EmailField(required=True, label="Email")
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    is_active = forms.BooleanField(required=False, initial=True, label="Active account")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.visible_fields():
            f.field.widget.attrs.setdefault("class", "form-control")

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        phone = re.sub(r"\s+", "", phone)
        if not phone:
            raise forms.ValidationError("Phone number is required")
        if phone.startswith("0") and len(phone) >= 10:
            phone = "254" + phone[1:]
        if CustomUser.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("This phone number is already registered")
        return phone

    def clean_email(self):
        em = (self.cleaned_data.get("email") or "").strip().lower()
        if not em:
            raise forms.ValidationError("Email is required for a director account.")
        if CustomUser.objects.filter(email=em).exists():
            raise forms.ValidationError("This email is already registered")
        return em

    def clean_full_name(self):
        n = (self.cleaned_data.get("full_name") or "").strip()
        if not n:
            raise forms.ValidationError("Full name is required")
        return n


class AssessmentForm(FormSettings):
    """Instructor creates/edits an assessment for their assigned course."""

    class Meta:
        model = Assessment
        fields = [
            "title",
            "description",
            "course",
            "session",
            "due_date",
            "file",
            "closes_at_deadline",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "due_date": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-control"},
                format="%Y-%m-%dT%H:%M",
            ),
            "closes_at_deadline": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, staff=None, **kwargs):
        self.staff = staff
        super().__init__(*args, **kwargs)
        for name in self.fields:
            if name != "closes_at_deadline":
                self.fields[name].widget.attrs.setdefault("class", "form-control")
        self.fields["due_date"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]
        if staff and staff.course_id:
            self.fields["course"].queryset = Course.objects.filter(pk=staff.course_id)
        elif staff:
            self.fields["course"].queryset = Course.objects.none()
        self.fields["session"].queryset = Session.objects.active_or_latest()
        self.fields["session"].empty_label = "Select intake/session"

    def clean_course(self):
        course = self.cleaned_data.get("course")
        if self.staff and self.staff.course_id:
            if not course or course.pk != self.staff.course_id:
                raise forms.ValidationError("You can only assign assessments to your assigned course.")
        return course


class SubmissionGradeForm(forms.Form):
    grade = forms.IntegerField(required=True, min_value=0, max_value=100)
    feedback = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grade"].widget.attrs.setdefault("class", "form-control")
