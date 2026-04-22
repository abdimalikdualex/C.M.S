from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *
# Register your models here.


class UserModel(UserAdmin):
    ordering = ('email',)


admin.site.register(CustomUser, UserModel)
admin.site.register(Staff)
admin.site.register(Student)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(Subject)
admin.site.register(Session)
admin.site.register(Payment)
admin.site.register(SmsLog)
admin.site.register(AuditLog)
admin.site.register(Assessment)
admin.site.register(Submission)
