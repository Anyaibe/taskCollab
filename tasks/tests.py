from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from datetime import date, timedelta

from .models import Task, Project, Comment, ProjectMembership


class AuthenticationTests(TestCase):
    """Tests for login, logout, and registration."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_login_valid_credentials_redirects_to_dashboard(self):
        """TC-01: Valid credentials should redirect to dashboard."""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_login_invalid_password_shows_error(self):
        """TC-02: Wrong password should show error message."""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password')

    def test_login_invalid_username_shows_error(self):
        """TC-03: Unknown username should show error message."""
        response = self.client.post(reverse('login'), {
            'username': 'unknownuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid username or password')

    def test_register_creates_account_and_redirects(self):
        """TC-04: Valid registration should create user and redirect."""
        response = self.client.post(reverse('register'), {
            'username':  'newuser',
            'email':     'new@test.com',
            'password1': 'newpass123',
            'password2': 'newpass123',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_mismatched_passwords_shows_error(self):
        """TC-05: Mismatched passwords should show error."""
        response = self.client.post(reverse('register'), {
            'username':  'anotheruser',
            'password1': 'pass123',
            'password2': 'different123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Passwords do not match')

    def test_logout_redirects_to_login(self):
        """TC-06: Logout should redirect to login page."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('login'))


class DashboardTests(TestCase):
    """Tests for dashboard access and content."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='dashuser',
            password='dashpass123'
        )

    def test_dashboard_requires_login(self):
        """TC-07: Unauthenticated access should redirect to login."""
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, '/login/?next=/dashboard/')

    def test_dashboard_loads_when_authenticated(self):
        """TC-08: Authenticated user should see dashboard with 200 OK."""
        self.client.login(username='dashuser', password='dashpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard')

    def test_dashboard_shows_correct_task_counts(self):
        """TC-09: Dashboard stat cards should show correct counts."""
        self.client.login(username='dashuser', password='dashpass123')

        project = Project.objects.create(
            name='Test Project',
            created_by=self.user
        )
        Task.objects.create(
            title='Pending Task', project=project,
            created_by=self.user, status='pending'
        )
        Task.objects.create(
            title='Done Task', project=project,
            created_by=self.user, status='completed'
        )

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['total_tasks'], 2)
        self.assertEqual(response.context['pending_tasks'], 1)
        self.assertEqual(response.context['completed_tasks'], 1)


class ProjectTests(TestCase):
    """Tests for project creation and management."""

    def setUp(self):
        self.client = Client()
        self.leader = User.objects.create_user(
            username='leader',
            password='leaderpass'
        )
        self.client.login(username='leader', password='leaderpass')

    def test_create_project_appears_in_list(self):
        """TC-10: Created project should appear in project list."""
        self.client.post(reverse('project_create'), {
            'name':        'My Test Project',
            'description': 'A project for testing',
        })
        self.assertTrue(Project.objects.filter(name='My Test Project').exists())

    def test_project_creator_assigned_as_leader(self):
        """TC-11: Project creator should be auto-assigned as Project Leader."""
        self.client.post(reverse('project_create'), {
            'name': 'Leadership Project',
        })
        project = Project.objects.get(name='Leadership Project')
        membership = ProjectMembership.objects.get(
            project=project, user=self.leader
        )
        self.assertEqual(membership.role, 'leader')

    def test_project_list_requires_login(self):
        """TC-12: Project list should require authentication."""
        self.client.logout()
        response = self.client.get(reverse('project_list'))
        self.assertEqual(response.status_code, 302)


class TaskTests(TestCase):
    """Tests for task creation, assignment, and permissions."""

    def setUp(self):
        self.client = Client()
        self.leader = User.objects.create_user(
            username='taskleader',
            password='leaderpass'
        )
        self.member = User.objects.create_user(
            username='taskmember',
            password='memberpass'
        )
        self.project = Project.objects.create(
            name='Task Project',
            created_by=self.leader
        )

    def test_task_create_appears_on_dashboard(self):
        """TC-13: Created task should appear on creator's dashboard."""
        self.client.login(username='taskleader', password='leaderpass')
        self.client.post(reverse('task_create'), {
            'title':       'New Test Task',
            'description': 'Test description',
            'project':     self.project.pk,
            'assigned_to': [self.leader.pk],
            'priority':    'high',
            'status':      'pending',
        })
        self.assertTrue(Task.objects.filter(title='New Test Task').exists())

    def test_non_leader_cannot_edit_task(self):
        """TC-14: Non-leader should be redirected when trying to edit a task."""
        task = Task.objects.create(
            title='Leader Task',
            project=self.project,
            created_by=self.leader,
            status='pending'
        )
        self.client.login(username='taskmember', password='memberpass')
        response = self.client.get(reverse('task_edit', args=[task.pk]))
        self.assertRedirects(response, reverse('dashboard'))

    def test_leader_can_edit_task(self):
        """TC-15: Project leader should be able to access task edit page."""
        task = Task.objects.create(
            title='Editable Task',
            project=self.project,
            created_by=self.leader,
            status='pending'
        )
        self.client.login(username='taskleader', password='leaderpass')
        response = self.client.get(reverse('task_edit', args=[task.pk]))
        self.assertEqual(response.status_code, 200)

    def test_non_leader_cannot_delete_task(self):
        """TC-16: Non-leader should be redirected when trying to delete a task."""
        task = Task.objects.create(
            title='Protected Task',
            project=self.project,
            created_by=self.leader,
            status='pending'
        )
        self.client.login(username='taskmember', password='memberpass')
        response = self.client.post(reverse('task_delete', args=[task.pk]))
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_assigned_user_can_update_status(self):
        """TC-17: Assigned user should be able to update task status."""
        task = Task.objects.create(
            title='Assigned Task',
            project=self.project,
            created_by=self.leader,
            status='pending'
        )
        task.assigned_to.add(self.member)

        self.client.login(username='taskmember', password='memberpass')
        self.client.post(reverse('task_update_status', args=[task.pk]), {
            'status': 'in_progress'
        })
        task.refresh_from_db()
        self.assertEqual(task.status, 'in_progress')


class CommentTests(TestCase):
    """Tests for task comments."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='commenter',
            password='commentpass'
        )
        self.project = Project.objects.create(
            name='Comment Project',
            created_by=self.user
        )
        self.task = Task.objects.create(
            title='Commented Task',
            project=self.project,
            created_by=self.user,
            status='pending'
        )

    def test_post_comment_appears_on_task_detail(self):
        """TC-18: Posted comment should appear on task detail page."""
        self.client.login(username='commenter', password='commentpass')
        self.client.post(reverse('task_detail', args=[self.task.pk]), {
            'body': 'This is a test comment'
        })
        self.assertTrue(
            Comment.objects.filter(
                task=self.task,
                body='This is a test comment'
            ).exists()
        )

    def test_task_detail_requires_login(self):
        """TC-19: Task detail page should require authentication."""
        response = self.client.get(
            reverse('task_detail', args=[self.task.pk])
        )
        self.assertEqual(response.status_code, 302)

    def test_task_detail_shows_existing_comments(self):
        """TC-20: Task detail page should display existing comments."""
        Comment.objects.create(
            task=self.task,
            author=self.user,
            body='Existing comment'
        )
        self.client.login(username='commenter', password='commentpass')
        response = self.client.get(
            reverse('task_detail', args=[self.task.pk])
        )
        self.assertContains(response, 'Existing comment')