from django.urls import path
from . import views

urlpatterns = [
    # User Module - Listings & Discovery
    path('', views.item_list, name='home'), # Home page of website.
    path('about/', views.about_view, name='about'), # About page of website.
    path('help/', views.help_view, name='help'), # Help page of website.
    path('items/create/', views.item_create, name='item_create'), # Calls item_create(). Used when a user wants to list an item to give away.
    path('items/<int:pk>/', views.item_detail, name='item_detail'), # Calls item_detail(). Used when a user wants to view an item.
    path('items/<int:pk>/edit/', views.item_edit, name='item_edit'), # Calls item_edit(). Used when a user wants to edit an item.
    path('items/<int:pk>/delete/', views.item_delete, name='item_delete'), # Calls item_delete(). Used when a user wants to delete an item.
    path('items/<int:pk>/request/', views.request_item, name='request_item'), # Calls request_item(). Used when a user wants to request an item.
    path('items/<int:pk>/mark-given/', views.mark_given_away, name='mark_given_away'), # Calls mark_given_away(). Used when a user wants to mark an item as given away.
    path('items/<int:pk>/mark-available/', views.mark_available, name='mark_available'), # Calls mark_available(). Used when a user wants to mark an item as available.
    path('items/<int:pk>/report/', views.report_item, name='report_item'), # Calls report_item(). Used when a user wants to report an item.

    # Request responses (Donor actions)
    path('requests/<int:request_id>/<str:action>/', views.respond_request, name='respond_request'), # Calls respond_request(). Used when a user wants to respond to a request.

    # User Dashboards & Public Community Profiles
    path('my-listings/', views.my_listings, name='my_listings'), # Calls my_listings(). Used when a user wants to view their listings.
    path('my-requests/', views.my_requests, name='my_requests'), # Calls my_requests(). Used when a user wants to view their requests.
    path('notifications/', views.notifications_view, name='notifications'), # Calls notifications_view(). Used when a user wants to view their notifications.
    path('profile/', views.profile_view, name='profile'), # Calls profile_view(). Used when a user wants to view their profile.
    path('profile/<str:username>/', views.public_profile_view, name='public_profile'), # Calls public_profile_view(). Used when a user wants to view another user's profile.
    path('profile/<str:username>/report/', views.report_user_view, name='report_user'), # Calls report_user_view(). Used when a user wants to report another user.
    path('reviews/create/<int:request_id>/', views.submit_review_view, name='submit_review'), # Calls submit_review_view(). Used when a user wants to submit a review.

    # Authentication & Email Verification
    path('register/', views.register_view, name='register'), # Calls register_view(). Used when a user wants to register.
    path('verify-email/', views.verify_otp_view, name='verify_otp'), # Calls verify_otp_view(). Used when a user wants to verify their email.
    path('resend-otp/', views.resend_otp_view, name='resend_otp'), # Calls resend_otp_view(). Used when a user wants to resend their OTP.
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Password Reset Flow
    path('password-reset/', views.password_reset_request_view, name='password_reset'), # Calls password_reset_request_view(). Used when a user wants to reset their password.
    path('password-reset/done/', views.password_reset_done_view, name='password_reset_done'), # Calls password_reset_done_view(). Used when a user wants to reset their password.
    path('password-reset-confirm/<uidb64>/<token>/', views.password_reset_confirm_view, name='password_reset_confirm'), # Calls password_reset_confirm_view(). Used when a user wants to confirm their password reset.
    path('password-reset-complete/', views.password_reset_complete_view, name='password_reset_complete'), # Calls password_reset_complete_view(). Used when a user wants to complete their password reset.

    # Admin Module
    path('platform-admin/', views.admin_dashboard, name='admin_dashboard'), # Calls admin_dashboard(). Used when an admin wants to view the admin dashboard.
    path('platform-admin/listings/', views.admin_listings, name='admin_listings'), # Calls admin_listings(). Used when an admin wants to view the admin listings.
    path('platform-admin/listings/<int:pk>/<str:action>/', views.admin_moderate_action, name='admin_moderate_action'), # Calls admin_moderate_action(). Used when an admin wants to moderate an item.
    path('platform-admin/categories/', views.admin_categories, name='admin_categories'), # Calls admin_categories(). Used when an admin wants to view the admin categories.
    path('platform-admin/categories/<int:pk>/delete/', views.admin_category_delete, name='admin_category_delete'), # Calls admin_category_delete(). Used when an admin wants to delete a category.
    path('platform-admin/reports/', views.admin_reports, name='admin_reports'), # Calls admin_reports(). Used when an admin wants to view the admin reports.
    path('platform-admin/reports/<int:pk>/<str:action>/', views.admin_report_resolve, name='admin_report_resolve'), # Calls admin_report_resolve(). Used when an admin wants to resolve a report.
    path('platform-admin/users/', views.admin_users, name='admin_users'), # Calls admin_users(). Used when an admin wants to view the admin users.
    path('platform-admin/users/<int:pk>/toggle/', views.admin_user_toggle_status, name='admin_user_toggle_status'), # Calls admin_user_toggle_status(). Used when an admin wants to toggle a user's status.
    path('platform-admin/users/<int:pk>/verify/', views.admin_user_toggle_verification, name='admin_user_toggle_verification'), # Calls admin_user_toggle_verification(). Used when an admin wants to toggle a user's verification.
]
