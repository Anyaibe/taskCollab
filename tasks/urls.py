from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),
    path('register/', views.register_view, name='register'),

    # Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),

    # Projects
    path('projects/',              views.project_list,   name='project_list'),
    path('projects/create/',       views.project_create, name='project_create'),
    path('projects/<int:pk>/',     views.project_detail, name='project_detail'),
    path('projects/<int:pk>/delete/', views.project_delete, name='project_delete'),

    # Tasks
    path('tasks/create/',             views.task_create,        name='task_create'),
    path('tasks/<int:pk>/edit/',      views.task_edit,          name='task_edit'),
    path('tasks/<int:pk>/delete/',    views.task_delete,        name='task_delete'),
    path('tasks/<int:pk>/status/',    views.task_update_status, name='task_update_status'),

    path('projects/<int:pk>/add-member/',              views.project_add_member,    name='project_add_member'),
    path('projects/<int:pk>/remove-member/<int:user_id>/', views.project_remove_member, name='project_remove_member'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('profile/', views.profile_view, name='profile'),
    path('search/', views.search_view, name='search'),
    path('notifications/', views.notifications_view, name='notifications'),
    path('projects/<int:pk>/invite/',        views.invite_member,     name='invite_member'),
    path('invitations/<uuid:token>/accept/', views.accept_invitation, name='accept_invitation'),
    path('invitations/<uuid:token>/decline/',views.decline_invitation,name='decline_invitation'),
    path('projects/<int:pk>/upload/',    views.upload_file, name='upload_file'),
    path('files/<int:file_pk>/delete/',  views.delete_file, name='delete_file'),
]