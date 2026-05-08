from django.core.mail import send_mail
from django.conf import settings
from .models import Task, Project, Comment, ProjectMembership, ActivityLog, Notification, ProjectInvitation
import calendar
import re
from datetime import date, timedelta
from django.utils import timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q

from .models import Task, Project, Comment, ProjectMembership, ActivityLog, Notification, ProjectInvitation, SharedFile

from .forms import ProjectForm, TaskForm

# Login

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username    = request.POST.get('username', '').strip()
        password    = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me')   # ← new

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Remember Me — keep session for 30 days, else end on browser close
            if remember_me:
                request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
            else:
                request.session.set_expiry(0)   # expires when browser closes

            return redirect('dashboard')

        return render(request, 'registration/login.html', {
            'error': 'Invalid username or password. Please try again.'
        })

    return render(request, 'registration/login.html')


# LOGOUT 

def logout_view(request):
    logout(request)
    return redirect('login')


# ─── REGISTER ─────────────────────────────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username  = request.POST.get('username', '').strip()
        email     = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        # ── Validation ──────────────────────────────────────
        if not username or not email or not password1:
            return render(request, 'registration/register.html',
                          {'error': 'All fields are required.'})

        # Real email format check
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return render(request, 'registration/register.html',
                          {'error': 'Please enter a valid email address.'})

        if User.objects.filter(email=email).exists():
            return render(request, 'registration/register.html',
                          {'error': 'An account with this email already exists.'})

        if User.objects.filter(username=username).exists():
            return render(request, 'registration/register.html',
                          {'error': f'Username "{username}" is already taken.'})

        if password1 != password2:
            return render(request, 'registration/register.html',
                          {'error': 'Passwords do not match.'})

        # Password strength rules
        if len(password1) < 8:
            return render(request, 'registration/register.html',
                          {'error': 'Password must be at least 8 characters long.'})

        if not re.search(r'[A-Za-z]', password1):
            return render(request, 'registration/register.html',
                          {'error': 'Password must contain at least one letter.'})

        if not re.search(r'[0-9]', password1):
            return render(request, 'registration/register.html',
                          {'error': 'Password must contain at least one number.'})

        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', password1):
            return render(request, 'registration/register.html',
                          {'error': 'Password must contain at least one special character (!@#$%^&* etc).'})

        # ── Create user ──────────────────────────────────────
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1
        )
        login(request, user)
        messages.success(request, f'Welcome, {username}! Your account has been created.')
        return redirect('dashboard')

    return render(request, 'registration/register.html')


# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@login_required(login_url='login')
def dashboard_view(request):
    user = request.user

    # All tasks visible to this user
    all_tasks = Task.objects.filter(
        Q(assigned_to=user) | Q(created_by=user)
    ).select_related('project').distinct()

    total_tasks      = all_tasks.count()
    pending_tasks    = all_tasks.filter(status='pending').count()
    inprogress_tasks = all_tasks.filter(status='in_progress').count()
    completed_tasks  = all_tasks.filter(status='completed').count()

    today = date.today()

    # Upcoming — all incomplete tasks with due dates
    upcoming_raw = Task.objects.filter(
        Q(assigned_to=user) | Q(created_by=user)
    ).exclude(status='completed').exclude(due_date=None).distinct().order_by('due_date')

    upcoming_tasks = []
    for task in upcoming_raw:
        days_left = (task.due_date - today).days
        upcoming_tasks.append({
            'title':    task.title,
            'status':   task.status,
            'due_date': task.due_date,
            'days_left': days_left,
            'pk':       task.pk,
        })

    # Recent comments on tasks the user can see
    recent_comments = Comment.objects.filter(
        task__in=all_tasks
    ).select_related('author', 'task').order_by('-created_at')[:5]

    # Calendar
    year, month = today.year, today.month
    current_month_year = today.strftime('%B %Y')
    task_dates = set(
        all_tasks.exclude(due_date=None).values_list('due_date', flat=True)
    )
    task_dates = {d for d in task_dates if d is not None}
    first_weekday, _ = calendar.monthrange(year, month)
    sun_start_offset = (first_weekday + 1) % 7
    _, days_in_month = calendar.monthrange(year, month)
    calendar_days = [
        {'number': '', 'is_today': False, 'is_other_month': True, 'has_task': False}
        for _ in range(sun_start_offset)
    ]
    for d in range(1, days_in_month + 1):
        current_date = date(year, month, d)
        calendar_days.append({
            'number':         d,
            'is_today':       current_date == today,
            'is_other_month': False,
            'has_task':       current_date in task_dates,
        })

    # Projects belonging to this user
    projects = Project.objects.filter(created_by=user)

    # ── Team Members — only show users connected via accepted membership ──────────
    #
    # Logic:
    # 1. Get all projects the current user is involved in (created or member of)
    # 2. Find all ProjectMembership records for those projects
    # 3. Collect the unique users from those memberships
    # 4. Exclude the current user, admins, and users with no membership connection
    # All project IDs this user is involved with
    involved_project_ids = set(
        list(projects.values_list('pk', flat=True)) +
        list(ProjectMembership.objects.filter(user=user).values_list('project_id', flat=True))
    )
    # All users who have an accepted membership on any of those projects
    # excluding the current user and superusers
    team_member_users = User.objects.filter(
        memberships__project_id__in=involved_project_ids,
        is_active=True,
        is_superuser=False
    ).exclude(pk=user.pk).distinct()[:6]
    # Build the team_members list with role information
    team_members = []
    for member in team_member_users:
        is_leader = Project.objects.filter(created_by=member).exists()
        if is_leader:
            role_display = '👑 Project Leader'
        else:
            membership = ProjectMembership.objects.filter(
                user=member,
                project_id__in=involved_project_ids
            ).first()
            role_display = membership.get_role_display() if membership else 'Team Member'
        team_members.append({
            'username':  member.username,
            'full_name': member.get_full_name() or member.username,
            'email':     member.email,
            'initial':   member.username[0].upper(),
            'role':      role_display,
            'is_leader': is_leader,
        })

    # Current logged-in user role
    current_user_is_leader = Project.objects.filter(created_by=user).exists()
    if current_user_is_leader:
        current_user_role = '👑 Project Leader'
    else:
        my_membership = ProjectMembership.objects.filter(user=user).first()
        current_user_role = my_membership.get_role_display() if my_membership else 'Team Member'

    # Activity logs for projects the user owns or is part of
    user_project_ids = list(projects.values_list('pk', flat=True))
    member_project_ids = list(
        ProjectMembership.objects.filter(user=user).values_list('project_id', flat=True)
    )
    all_project_ids = list(set(user_project_ids + member_project_ids))

    activity_logs = ActivityLog.objects.filter(
        project_id__in=all_project_ids
    ).select_related('user', 'task', 'project').order_by('-created_at')[:8]

    notif_count = Notification.objects.filter(
        recipient=user, is_read=False
    ).count()

    context = {
        'tasks':                  all_tasks,
        'total_tasks':            total_tasks,
        'pending_tasks':          pending_tasks,
        'inprogress_tasks':       inprogress_tasks,
        'completed_tasks':        completed_tasks,
        'upcoming_tasks':         upcoming_tasks,
        'upcoming_count':         upcoming_raw.count(),
        'calendar_days':          calendar_days,
        'current_month_year':     current_month_year,
        'team_members':           team_members,
        'projects':               projects,
        'recent_comments':        recent_comments,
        'now':                    timezone.now(),
        'current_user_role':      current_user_role,
        'current_user_is_leader': current_user_is_leader,
        'activity_logs': activity_logs,
        'notif_count': notif_count,
    }
    return render(request, 'tasks/dashboard.html', context)


# ─── PROJECT VIEWS ────────────────────────────────────────────────────────────

@login_required(login_url='login')
def project_list(request):
    projects = Project.objects.filter(created_by=request.user).order_by('-created_at')
    return render(request, 'tasks/project_list.html', {'projects': projects})


@login_required(login_url='login')
def project_create(request):
    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user
            project.save()
            # Automatically assign creator as Project Leader
            ProjectMembership.objects.create(
                project=project,
                user=request.user,
                role='leader'
            )
            ActivityLog.objects.create(
                user=request.user,
                project=project,
                action=f'Created project "{project.name}"'
            )
            messages.success(request, f'Project "{project.name}" created successfully!')
            return redirect('project_list')
    else:
        form = ProjectForm()
    return render(request, 'tasks/project_form.html', {
        'form': form, 'title': 'Create Project'
    })


@login_required(login_url='login')
def project_detail(request, pk):
    project     = get_object_or_404(Project, pk=pk)
    tasks       = Task.objects.filter(project=project).prefetch_related('assigned_to').select_related('created_by')
    memberships = ProjectMembership.objects.filter(project=project).select_related('user')

    existing_user_ids = list(memberships.values_list('user_id', flat=True))
    existing_user_ids.append(project.created_by.pk)
    available_users = User.objects.filter(
        is_active=True,
        is_superuser=False
    ).exclude(pk__in=existing_user_ids)

    total_tasks      = tasks.count()
    completed_count  = tasks.filter(status='completed').count()
    inprogress_count = tasks.filter(status='in_progress').count()
    pending_count    = tasks.filter(status='pending').count()
    progress         = int((completed_count / total_tasks * 100) if total_tasks > 0 else 0)

    return render(request, 'tasks/project_detail.html', {
        'project':         project,
        'tasks':           tasks,
        'memberships':     memberships,
        'available_users': available_users,
        'total_tasks':     total_tasks,
        'completed_count': completed_count,
        'inprogress_count': inprogress_count,
        'pending_count':   pending_count,
        'progress':        progress,
    })


@login_required(login_url='login')
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk, created_by=request.user)
    if request.method == 'POST':
        name = project.name
        project.delete()
        messages.success(request, f'Project "{name}" deleted.')
        return redirect('project_list')
    return render(request, 'tasks/confirm_delete.html', {
        'object': project, 'type': 'Project'
    })


# ─── TASK VIEWS ───────────────────────────────────────────────────────────────

@login_required(login_url='login')
def task_create(request):
    if request.method == 'POST':
        form = TaskForm(request.POST, user=request.user)
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()
            ActivityLog.objects.create(
                user=request.user,
                task=task,
                project=task.project,
                action=f'Created task "{task.title}"'
            )
            form.save_m2m()  # save ManyToMany assigned_to
            for assigned_user in task.assigned_to.all():
                if assigned_user != request.user:
                    Notification.objects.create(
                        recipient=assigned_user,
                        message=f'{request.user.username} assigned you to task "{task.title}"',
                        link=f'/tasks/{task.pk}/'
                    )
            messages.success(request, f'Task "{task.title}" created successfully!')
            return redirect('dashboard')
    else:
        form = TaskForm(user=request.user)
    return render(request, 'tasks/task_form.html', {'form': form, 'title': 'Create Task'})


@login_required(login_url='login')
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)

    if request.user != task.project.created_by:
        messages.error(request, 'Only the Project Leader can edit tasks.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, user=request.user)
        if form.is_valid():
            form.save()
            for assigned_user in task.assigned_to.all():
                if assigned_user != request.user:
                    Notification.objects.create(
                        recipient=assigned_user,
                        message=f'{request.user.username} updated task "{task.title}" — you are assigned',
                        link=f'/tasks/{task.pk}/'
                    )
            ActivityLog.objects.create(
                user=request.user,
                task=task,
                project=task.project,
                action=f'Created task "{task.title}"'
            )
            messages.success(request, f'Task "{task.title}" updated successfully!')
            return redirect('dashboard')
    else:
        form = TaskForm(instance=task, user=request.user)
    return render(request, 'tasks/task_form.html', {
        'form': form, 'title': 'Edit Task'
    })


@login_required(login_url='login')
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)

    if request.user != task.project.created_by:
        messages.error(request, 'Only the Project Leader can delete tasks.')
        return redirect('dashboard')

    if request.method == 'POST':
        name    = task.title
        project = task.project   # save reference BEFORE deleting

        task.delete()            # delete the task FIRST

        # Log AFTER deletion — no task reference passed
        ActivityLog.objects.create(
            user=request.user,
            project=project,     # use the saved reference
            action=f'Deleted task "{name}"'
        )
        messages.success(request, f'Task "{name}" deleted.')
        return redirect('dashboard')

    return render(request, 'tasks/confirm_delete.html', {
        'object': task, 'type': 'Task'
    })


@login_required(login_url='login')
def task_update_status(request, pk):
    task = get_object_or_404(Task, pk=pk)

    # Allow project leader OR any assigned user to update status
    is_leader   = request.user == task.project.created_by
    is_assigned = task.assigned_to.filter(pk=request.user.pk).exists()

    if not is_leader and not is_assigned:
        messages.error(request, 'You do not have permission to update this task.')
        return redirect('dashboard')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['pending', 'in_progress', 'completed']:
            task.status = new_status
            task.save()
            ActivityLog.objects.create(
                user=request.user,
                task=task,
                project=task.project,
                action=f'Created task "{task.title}"'
            )
            messages.success(request, f'Status updated to "{task.get_status_display()}".')
    return redirect('dashboard')


@login_required(login_url='login')
def project_add_member(request, pk):
    project = get_object_or_404(Project, pk=pk, created_by=request.user)
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        role    = request.POST.get('role', 'member')
        try:
            member_user = User.objects.get(pk=user_id)
            membership, created = ProjectMembership.objects.get_or_create(
                project=project, user=member_user,
                defaults={'role': role}
            )
            if not created:
                membership.role = role
                membership.save()
                ActivityLog.objects.create(
                    user=request.user,
                    project=project,
                    action=f'Created project "{project.name}"'
                )
            messages.success(request, f'{member_user.username} added as {membership.get_role_display()}.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
    return redirect('project_detail', pk=pk)


@login_required(login_url='login')
def project_remove_member(request, pk, user_id):
    project = get_object_or_404(Project, pk=pk, created_by=request.user)
    membership = get_object_or_404(ProjectMembership, project=project, user_id=user_id)
    if request.method == 'POST':
        username = membership.user.username
        membership.delete()
        ActivityLog.objects.create(
            user=request.user,
            project=project,
            action=f'Created project "{project.name}"'
        )
        messages.success(request, f'{username} removed from project.')
    return redirect('project_detail', pk=pk)


@login_required(login_url='login')
def task_detail(request, pk):
    task     = get_object_or_404(Task, pk=pk)
    comments = Comment.objects.filter(task=task).select_related('author').order_by('created_at')

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            Comment.objects.create(
                task=task,
                author=request.user,
                body=body
            )
            messages.success(request, 'Comment posted.')
        return redirect('task_detail', pk=pk)

    return render(request, 'tasks/task_detail.html', {
        'task':     task,
        'comments': comments,
    })

@login_required(login_url='login')
def profile_view(request):
    user = request.user

    # Update profile if form submitted
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        email      = request.POST.get('email', '').strip()

        user.first_name = first_name
        user.last_name  = last_name
        user.email      = email
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('profile')

    # User's projects
    my_projects = Project.objects.filter(created_by=user).order_by('-created_at')

    # Projects user is a member of (not created by them)
    member_projects = ProjectMembership.objects.filter(
        user=user
    ).exclude(
        project__created_by=user
    ).select_related('project')

    # Task stats
    all_tasks        = Task.objects.filter(Q(assigned_to=user) | Q(created_by=user)).distinct()
    total_tasks      = all_tasks.count()
    pending_tasks    = all_tasks.filter(status='pending').count()
    inprogress_tasks = all_tasks.filter(status='in_progress').count()
    completed_tasks  = all_tasks.filter(status='completed').count()

    # User's role
    is_leader = Project.objects.filter(created_by=user).exists()
    if is_leader:
        role = '👑 Project Leader'
    else:
        membership = ProjectMembership.objects.filter(user=user).first()
        role = membership.get_role_display() if membership else 'Team Member'

    # Recent comments by this user
    recent_comments = Comment.objects.filter(
        author=user
    ).select_related('task').order_by('-created_at')[:5]

    context = {
        'my_projects':       my_projects,
        'member_projects':   member_projects,
        'total_tasks':       total_tasks,
        'pending_tasks':     pending_tasks,
        'inprogress_tasks':  inprogress_tasks,
        'completed_tasks':   completed_tasks,
        'role':              role,
        'is_leader':         is_leader,
        'recent_comments':   recent_comments,
    }
    return render(request, 'tasks/profile.html', context)

@login_required(login_url='login')
def search_view(request):
    query    = request.GET.get('q', '').strip()
    tasks    = []
    projects = []

    if query:
        tasks = Task.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        ).filter(
            Q(assigned_to=request.user) | Q(created_by=request.user)
        ).select_related('project').distinct()

        projects = Project.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        ).filter(
            Q(created_by=request.user) |
            Q(memberships__user=request.user)
        ).distinct()

    return render(request, 'tasks/search_results.html', {
        'query':    query,
        'tasks':    tasks,
        'projects': projects,
    })

@login_required(login_url='login')
def notifications_view(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')[:20]

    # Mark all as read when page is opened
    Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)

    return render(request, 'tasks/notifications.html', {
        'notifications': notifications,
    })

@login_required(login_url='login')
def invite_member(request, pk):
    project = get_object_or_404(Project, pk=pk, created_by=request.user)

    if request.method == 'POST':
        query = request.POST.get('search_query', '').strip()
        role  = request.POST.get('role', 'member')

        if not query:
            messages.error(request, 'Please enter a username or email to search.')
            return redirect('project_detail', pk=pk)

        found_user = User.objects.filter(
            Q(username__iexact=query) | Q(email__iexact=query),
            is_active=True,
            is_superuser=False
        ).first()

        if not found_user:
            messages.error(request, f'No user found with username or email "{query}".')
            return redirect('project_detail', pk=pk)

        if found_user == request.user:
            messages.error(request, 'You cannot invite yourself.')
            return redirect('project_detail', pk=pk)

        if ProjectMembership.objects.filter(project=project, user=found_user).exists():
            messages.error(request, f'{found_user.username} is already a member.')
            return redirect('project_detail', pk=pk)

        existing = ProjectInvitation.objects.filter(
            project=project, email=found_user.email
        ).first()

        if existing and existing.status == 'pending':
            messages.error(request, f'Invitation already sent to {found_user.email}.')
            return redirect('project_detail', pk=pk)

        # Create invitation record
        invitation = ProjectInvitation.objects.create(
            project=project,
            invited_by=request.user,
            email=found_user.email,
        )

        accept_url  = f"{request.scheme}://{request.get_host()}/invitations/{invitation.token}/accept/"
        decline_url = f"{request.scheme}://{request.get_host()}/invitations/{invitation.token}/decline/"

        # Send email — catch errors so page doesn't crash
        try:
            send_mail(
                subject=f'Invitation to join "{project.name}" on TaskCollab',
                message=f"""Hi {found_user.username},

{request.user.username} has invited you to join the project "{project.name}" on TaskCollab.

Accept invitation:
{accept_url}

Decline invitation:
{decline_url}

This invitation will remain open until you respond.

— The TaskCollab Team""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[found_user.email],
                fail_silently=False,
            )
            messages.success(request, f'Invitation sent to {found_user.email}.')
        except Exception as e:
            # Delete the invitation if email failed
            invitation.delete()
            messages.error(request, f'Failed to send invitation email. Please check your email settings. Error: {str(e)}')
            return redirect('project_detail', pk=pk)

        ActivityLog.objects.create(
            user=request.user,
            project=project,
            action=f'Sent invitation to {found_user.username} for "{project.name}"'
        )

    return redirect('project_detail', pk=pk)


def accept_invitation(request, token):
    """User clicks the accept link from their email."""
    invitation = get_object_or_404(ProjectInvitation, token=token)

    if invitation.status != 'pending':
        messages.error(request, 'This invitation has already been responded to.')
        return redirect('dashboard' if request.user.is_authenticated else 'login')

    # Find the user by email
    try:
        invited_user = User.objects.get(email=invitation.email)
    except User.DoesNotExist:
        messages.error(request, 'No account found for this invitation email.')
        return redirect('login')

    # If not logged in, redirect to login first
    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/invitations/{token}/accept/')

    if request.user != invited_user:
        messages.error(request, 'This invitation was sent to a different account.')
        return redirect('dashboard')

    # Accept: create membership
    invitation.status = 'accepted'
    invitation.save()

    membership, created = ProjectMembership.objects.get_or_create(
        project=invitation.project,
        user=invited_user,
        defaults={'role': 'member'}
    )

    # Notify the project creator
    Notification.objects.create(
        recipient=invitation.invited_by,
        message=f'{invited_user.username} accepted your invitation to "{invitation.project.name}"',
        link=f'/projects/{invitation.project.pk}/'
    )

    # Send email to project creator
    send_mail(
        subject=f'{invited_user.username} accepted your invitation',
        message=f"""
Hi {invitation.invited_by.username},

Good news! {invited_user.username} has accepted your invitation to join "{invitation.project.name}" on TaskCollab.

They are now a member of your project.
        """,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.invited_by.email],
        fail_silently=True,
    )

    ActivityLog.objects.create(
        user=invited_user,
        project=invitation.project,
        action=f'Accepted invitation and joined "{invitation.project.name}"'
    )

    messages.success(request, f'You have joined "{invitation.project.name}" successfully!')
    return redirect('project_detail', pk=invitation.project.pk)


def decline_invitation(request, token):
    """User clicks the decline link from their email."""
    invitation = get_object_or_404(ProjectInvitation, token=token)

    if invitation.status != 'pending':
        messages.error(request, 'This invitation has already been responded to.')
        return redirect('dashboard' if request.user.is_authenticated else 'login')

    invitation.status = 'declined'
    invitation.save()

    messages.info(request, f'You have declined the invitation to "{invitation.project.name}".')
    return redirect('dashboard' if request.user.is_authenticated else 'login')

@login_required(login_url='login')
def upload_file(request, pk):
    """Upload a file to a project."""
    project = get_object_or_404(Project, pk=pk)

    # Only project members or leader can upload
    is_leader = request.user == project.created_by
    is_member = ProjectMembership.objects.filter(
        project=project, user=request.user
    ).exists()

    if not is_leader and not is_member:
        messages.error(request, 'You must be a project member to upload files.')
        return redirect('project_detail', pk=pk)

    if request.method == 'POST' and request.FILES.get('file'):
        uploaded = request.FILES['file']
        description = request.POST.get('description', '').strip()

        shared_file = SharedFile.objects.create(
            project=project,
            uploaded_by=request.user,
            file=uploaded,
            filename=uploaded.name,
            description=description
        )

        # Notify all project members
        members = ProjectMembership.objects.filter(
            project=project
        ).exclude(user=request.user).select_related('user')

        for m in members:
            Notification.objects.create(
                recipient=m.user,
                message=f'{request.user.username} uploaded "{uploaded.name}" to "{project.name}"',
                link=f'/projects/{project.pk}/'
            )

        # Also notify the leader if uploader is not the leader
        if not is_leader:
            Notification.objects.create(
                recipient=project.created_by,
                message=f'{request.user.username} uploaded "{uploaded.name}" to "{project.name}"',
                link=f'/projects/{project.pk}/'
            )

        ActivityLog.objects.create(
            user=request.user,
            project=project,
            action=f'Uploaded file "{uploaded.name}" to "{project.name}"'
        )

        messages.success(request, f'"{uploaded.name}" uploaded successfully!')

    return redirect('project_detail', pk=pk)


@login_required(login_url='login')
def delete_file(request, file_pk):
    """Delete a shared file — only uploader or project leader can delete."""
    shared_file = get_object_or_404(SharedFile, pk=file_pk)
    project     = shared_file.project

    if request.user != shared_file.uploaded_by and request.user != project.created_by:
        messages.error(request, 'You do not have permission to delete this file.')
        return redirect('project_detail', pk=project.pk)

    if request.method == 'POST':
        name = shared_file.filename
        shared_file.file.delete(save=False)  # delete actual file from disk
        shared_file.delete()
        messages.success(request, f'"{name}" deleted.')

    return redirect('project_detail', pk=project.pk)
