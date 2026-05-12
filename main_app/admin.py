from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *
# Register your models here.


class UserModel(UserAdmin):
    ordering = ('email',)


class EnrollmentFeeAuditAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "previous_fee", "new_fee", "edited_by", "created_at")
    list_select_related = ("enrollment", "edited_by")
    readonly_fields = ("enrollment", "previous_fee", "new_fee", "edited_by", "created_at")


class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "admin", "course", "session", "enrollment_date")
    search_fields = (
        "student_id",
        "admin__email",
        "admin__full_name",
        "admin__first_name",
        "admin__last_name",
        "admin__phone_number",
    )
    readonly_fields = ("student_id",)


admin.site.register(CustomUser, UserModel)
admin.site.register(Staff)
admin.site.register(Student, StudentAdmin)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(EnrollmentFeeAudit, EnrollmentFeeAuditAdmin)
admin.site.register(Subject)
admin.site.register(Session)
admin.site.register(Payment)
admin.site.register(SmsLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "user_name",
        "user_role",
        "module",
        "audit_action",
        "activity",
        "legacy_event",
        "target_record",
        "ip_address",
    )
    list_filter = ("module", "audit_action", "created_at")
    search_fields = ("activity", "detail", "target_record", "user_name", "legacy_event", "module")
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


admin.site.register(AuditLog, AuditLogAdmin)
admin.site.register(Assessment)
admin.site.register(Submission)
admin.site.register(StudentHubProfile)
admin.site.register(HubEvent)
admin.site.register(HubEventRegistration)
admin.site.register(MentorNote)
admin.site.register(AdmissionSequence)
