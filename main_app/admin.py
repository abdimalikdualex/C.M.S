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


admin.site.register(CustomUser, UserModel)
admin.site.register(Staff)
admin.site.register(Student)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(EnrollmentFeeAudit, EnrollmentFeeAuditAdmin)
admin.site.register(Subject)
admin.site.register(Session)
admin.site.register(Payment)
admin.site.register(SmsLog)
admin.site.register(AuditLog)
admin.site.register(Assessment)
admin.site.register(Submission)
