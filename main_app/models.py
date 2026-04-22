from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import UserManager
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from django.db.models import Sum
from django.db.utils import OperationalError, ProgrammingError
import uuid

from .money import max_zero_kes, quantize_kes




class CustomUserManager(UserManager):
    def _create_user(self, email, password, **extra_fields):
        email = self.normalize_email(email)
        user = CustomUser(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        assert extra_fields["is_staff"]
        assert extra_fields["is_superuser"]
        return self._create_user(email, password, **extra_fields)


class Session(models.Model):
    class SessionQuerySet(models.QuerySet):
        def latest_first(self):
            return self.order_by("-start_year", "-end_year", "-id")

        def active(self):
            today = timezone.localdate()
            return self.filter(start_year__lte=today, end_year__gte=today).latest_first()

        def active_or_latest(self):
            active_qs = self.active()
            if active_qs.exists():
                return active_qs
            return self.latest_first()

    start_year = models.DateField()
    end_year = models.DateField()
    objects = SessionQuerySet.as_manager()

    @property
    def is_active(self) -> bool:
        today = timezone.localdate()
        return bool(self.start_year and self.end_year and self.start_year <= today <= self.end_year)

    @property
    def intake_label(self) -> str:
        return f"{self.start_year:%b %Y} Intake"

    def __str__(self):
        return f"{self.intake_label} ({self.start_year:%Y-%m-%d} to {self.end_year:%Y-%m-%d})"


class CustomUser(AbstractUser):
    USER_TYPE = ((1, "HOD"), (2, "Staff"), (3, "Student"))
    GENDER = [("M", "Male"), ("F", "Female")]
    
    
    username = None  # Removed username, using email instead
    email = models.EmailField(unique=True)
    full_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Full name as entered (single field). Used for display when set.",
    )
    phone_number = models.CharField(max_length=20, blank=True, default="")
    user_type = models.CharField(default=1, choices=USER_TYPE, max_length=1)
    gender = models.CharField(max_length=1, choices=GENDER)
    profile_pic = models.ImageField()
    address = models.TextField()
    fcm_token = models.TextField(default="")  # For firebase notifications
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = CustomUserManager()

    def __str__(self):
        full = (self.full_name or "").strip()
        if full:
            return full
        fn = (self.first_name or "").strip()
        ln = (self.last_name or "").strip()
        if fn and ln:
            return f"{fn} {ln}"
        if fn or ln:
            return fn or ln
        return self.email or str(self.pk)

    def get_full_name(self):
        """Prefer full_name, then first+last, then email (never last-first order)."""
        full = (self.full_name or "").strip()
        if full:
            return full
        fn = (self.first_name or "").strip()
        ln = (self.last_name or "").strip()
        combined = f"{fn} {ln}".strip()
        if combined:
            return combined
        return (self.email or "").strip() or str(self.pk)


class Admin(models.Model):
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)



class Course(models.Model):
    """
    Short-course line-up (examples): English/Kiswahili by level; ICT packages
    (Computer Packages, Graphic Design, Web Dev, Digital Marketing, Networking,
    Cybersecurity). Duration/fee/plan align with Kenyan short-course ops.
    """

    name = models.CharField(max_length=120)
    DURATION_UNIT = (("weeks", "Weeks"), ("months", "Months"))
    PAYMENT_PLAN = (("monthly", "Monthly"), ("full", "Full Course"))
    LANGUAGE_LEVEL = (
        ("", "N/A"),
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    )

    duration_value = models.PositiveIntegerField(default=0)
    duration_unit = models.CharField(max_length=10, choices=DURATION_UNIT, default="weeks")
    payment_plan = models.CharField(max_length=10, choices=PAYMENT_PLAN, default="full")
    monthly_fee = models.PositiveIntegerField(default=0)
    full_fee = models.PositiveIntegerField(default=0)
    level = models.CharField(max_length=20, choices=LANGUAGE_LEVEL, default="", blank=True)
    rolling_intake = models.BooleanField(default=True)
    intake_start = models.DateField(null=True, blank=True)
    intake_end = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def total_fee_for_student(self):
        """
        Total expected fee for a student on this course.
        For monthly plan: duration in months * monthly_fee (or weeks->ceil(weeks/4)).
        """
        if self.payment_plan == "monthly":
            if self.duration_value <= 0:
                return quantize_kes(self.monthly_fee)
            months = self.duration_value if self.duration_unit == "months" else max(1, (self.duration_value + 3) // 4)
            return quantize_kes(months * quantize_kes(self.monthly_fee))
        return quantize_kes(self.full_fee)

    def save(self, *args, **kwargs):
        self.full_fee = quantize_kes(self.full_fee or 0)
        self.monthly_fee = quantize_kes(self.monthly_fee or 0)
        super().save(*args, **kwargs)


class Student(models.Model):
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.DO_NOTHING, null=True, blank=False)
    session = models.ForeignKey(Session, on_delete=models.DO_NOTHING, null=True)
    student_id = models.CharField(max_length=32, unique=True, blank=True, default="")
    enrollment_date = models.DateField(default=timezone.now)

    def __str__(self):
        return str(self.admin)

    def total_fee(self):
        enrollments = self.enrollments.all()
        if enrollments.exists():
            total = sum((int(e.total_fee or 0) for e in enrollments), 0)
            return quantize_kes(total)
        if not self.course:
            return 0
        return quantize_kes(self.course.total_fee_for_student())

    def total_paid(self):
        try:
            agg = self.payments.aggregate(total=Sum("amount"))
            return quantize_kes(agg["total"] or 0)
        except (OperationalError, ProgrammingError):
            # DB schema drift fallback: keep pages usable even if payment FK
            # column is missing in a local SQLite file.
            return 0

    def balance(self):
        return max_zero_kes(self.total_fee() - self.total_paid())


class Enrollment(models.Model):
    STATUS = (("active", "Active"), ("completed", "Completed"), ("cancelled", "Cancelled"))
    LEVEL = (
        ("", "N/A"),
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    start_date = models.DateField(default=timezone.now)
    total_fee = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS, default="active")
    enrollment_level = models.CharField(max_length=20, choices=LEVEL, default="", blank=True)
    session = models.ForeignKey(Session, null=True, blank=True, on_delete=models.SET_NULL)
    assigned_instructor = models.ForeignKey(
        "Staff",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_enrollments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "course"], name="uniq_student_course_enrollment"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} - {self.course}"

    @property
    def amount_paid(self):
        return quantize_kes(self.payments.aggregate(total=Sum("amount")).get("total") or 0)

    @property
    def balance_due(self):
        return max_zero_kes(quantize_kes(self.total_fee or 0) - self.amount_paid)

    def save(self, *args, **kwargs):
        self.total_fee = quantize_kes(self.total_fee or 0)
        super().save(*args, **kwargs)


class Staff(models.Model):
    STAFF_ROLE = (
        ("instructor", "Instructor"),
        ("admission", "Admission Officer"),
        ("finance", "Finance"),
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        help_text="Teaching assignment: instructors should have a course; admission/finance may leave empty.",
    )
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=STAFF_ROLE, default="instructor")
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return str(self.admin)


class Subject(models.Model):
    name = models.CharField(max_length=120)
    staff = models.ForeignKey(Staff,on_delete=models.CASCADE,)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Attendance(models.Model):
    session = models.ForeignKey(Session, on_delete=models.DO_NOTHING)
    subject = models.ForeignKey(Subject, on_delete=models.DO_NOTHING)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AttendanceReport(models.Model):
    student = models.ForeignKey(Student, on_delete=models.DO_NOTHING)
    attendance = models.ForeignKey(Attendance, on_delete=models.CASCADE)
    status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeaveReportStudent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date = models.CharField(max_length=60)
    message = models.TextField()
    status = models.SmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeaveReportStaff(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    date = models.CharField(max_length=60)
    message = models.TextField()
    status = models.SmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FeedbackStudent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    feedback = models.TextField()
    reply = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FeedbackStaff(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    feedback = models.TextField()
    reply = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationStaff(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotificationStudent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class StudentResult(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    test = models.FloatField(default=0)
    exam = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Assessment(models.Model):
    """Homework / exercise / assessment assigned by an instructor to a course."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assessments")
    instructor = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="assessments_created",
        help_text="Instructor who created this assessment.",
    )
    session = models.ForeignKey(
        Session,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assessments",
        help_text="Optional intake/session scope.",
    )
    due_date = models.DateTimeField()
    file = models.FileField(upload_to="assessments/instructions/", blank=True, null=True)
    closes_at_deadline = models.BooleanField(
        default=False,
        help_text="If set, students cannot submit or update after the due date.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-due_date", "-created_at"]

    def __str__(self):
        return self.title

    def is_submitted(self, student) -> bool:
        return self.submissions.filter(student=student).exists()


class Submission(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="assessment_submissions")
    file = models.FileField(upload_to="assessments/submissions/", blank=True, null=True)
    text_answer = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    grade = models.IntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["assessment", "student"], name="uniq_assessment_student_submission"),
        ]
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.student} → {self.assessment}"


class AuditLog(models.Model):
    action = models.CharField(max_length=120)
    detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    student = models.ForeignKey(
        Student,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        CustomUser,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_actions",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class Payment(models.Model):
    MODE = (("cash", "Cash"), ("mpesa", "Mobile Money (M-Pesa)"))
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="payments")
    course = models.ForeignKey(Course, on_delete=models.DO_NOTHING, null=True, blank=True)
    amount = models.PositiveIntegerField()
    mode = models.CharField(max_length=10, choices=MODE, default="cash")
    receipt_no = models.CharField(max_length=40, unique=True, blank=True, default="")
    reference = models.CharField(max_length=80, blank=True, default="")  # e.g. M-Pesa code
    paid_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments_recorded",
        help_text="User who recorded this payment (audit).",
    )
    enrollment = models.ForeignKey(
        Enrollment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )

    def save(self, *args, **kwargs):
        self.amount = quantize_kes(self.amount or 0)
        if not self.course_id and self.student_id:
            self.course = self.student.course
        if not self.receipt_no:
            self.receipt_no = f"RCPT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
        # Per-enrollment balances are computed dynamically from related payments.


class SmsLog(models.Model):
    """Queued/logged SMS for Safaricom / Africa's Talking integration later."""

    REASON = (
        ("admission", "Admission confirmation"),
        ("payment", "Payment confirmation"),
        ("class_reminder", "Class reminder"),
    )
    STATUS = (
        ("logged", "Logged (not sent)"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    )
    to_phone = models.CharField(max_length=20)
    message = models.TextField()
    reason = models.CharField(max_length=20, choices=REASON)
    status = models.CharField(max_length=10, choices=STATUS, default="logged")
    created_at = models.DateTimeField(auto_now_add=True)
    payment = models.ForeignKey(
        Payment,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="sms_logs",
    )
    student = models.ForeignKey(
        Student,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="sms_logs",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reason} → {self.to_phone}"


def _ut_key(user_type):
    return str(user_type).strip()


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        ut = _ut_key(instance.user_type)
        if ut == "1":
            Admin.objects.create(admin=instance)
        if ut == "2":
            Staff.objects.create(admin=instance)
        if ut == "3":
            Student.objects.create(admin=instance)


@receiver(post_save, sender=CustomUser)
def save_user_profile(sender, instance, **kwargs):
    ut = _ut_key(instance.user_type)
    if ut == "1":
        instance.admin.save()
    if ut == "2":
        instance.staff.save()
    if ut == "3":
        instance.student.save()


@receiver(post_save, sender=Student)
def ensure_student_id(sender, instance, created, **kwargs):
    if instance.student_id:
        return
    # Kenyan-friendly, short, unique: STU-<YY><6chars>
    year = timezone.now().strftime("%y")
    token = uuid.uuid4().hex[:6].upper()
    instance.student_id = f"STU-{year}{token}"
    Student.objects.filter(pk=instance.pk).update(student_id=instance.student_id)
