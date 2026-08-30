from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from training import services
from training.models import Goal, Workout


@login_required
def home(request):
    user = request.user
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    weekly_volume = services.volume_since(user, week_start)
    monthly_volume = services.volume_since(user, month_start)
    weekly_sets = services.sets_since(user, week_start)
    weekly_workouts = services.workouts_since(user, week_start)

    context = {
        "current_workout": services.current_workout(user),
        "last_workout": services.last_workout(user),
        "next_routine_day": services.next_routine_day(user),
        "bodyweight_now": services.bodyweight_now(user),
        "bodyweight_trend": services.bodyweight_trend(user, days=90),
        "weekly_volume": weekly_volume,
        "monthly_volume": monthly_volume,
        "weekly_sets": weekly_sets,
        "weekly_workouts": weekly_workouts,
        "total_workouts": Workout.objects.filter(user=user, status=Workout.Status.COMPLETED).count(),
        "total_sets": services.sets_since(user, date(2000, 1, 1)),
        "total_time_hours": round(services.total_time_seconds(user) / 3600, 1),
        "recent_prs": services.recent_prs(user),
        "streak_days": services.current_streak_days(user),
        "active_goals": Goal.objects.filter(user=user, achieved=False).select_related("exercise")[:5],
        "muscle_groups_recent": services.muscle_groups_recent(user, days=7),
    }

    bw_labels = [row["date"].isoformat() for row in context["bodyweight_trend"]]
    bw_values = [float(row["weight_kg"]) for row in context["bodyweight_trend"]]
    context["bodyweight_chart_labels"] = bw_labels
    context["bodyweight_chart_values"] = bw_values

    volume_labels, volume_values = services.weekly_volume_series(user, weeks=12)
    context["volume_chart_labels"] = volume_labels
    context["volume_chart_values"] = [float(v) for v in volume_values]
    context["has_volume_data"] = any(v > 0 for v in volume_values)

    return render(request, "dashboard/home.html", context)
