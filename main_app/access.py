"""Role checks shared across views (fee editing, etc.)."""


def user_can_edit_assigned_course_fees(user) -> bool:
    """
    Superadmin lane only: HOD (1), legacy Director (4), or Django superuser.
    Instructors, admission/finance staff, and students cannot edit assigned fees.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    ut = str(getattr(user, "user_type", "") or "").strip()
    return ut in ("1", "4")
