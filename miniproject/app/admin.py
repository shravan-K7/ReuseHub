from django.contrib import admin
from .models import Category, Item, ItemImage, ItemRequest, Report, UserProfile, EmailOTP, SupportInquiry


class ItemImageInline(admin.TabularInline):
    model = ItemImage
    extra = 1
    fields = ('image', 'is_cover', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    inlines = [ItemImageInline]
    list_display = ('title', 'donor', 'category', 'condition', 'is_repairable', 'status', 'moderation_status', 'created_at')
    list_filter = ('status', 'moderation_status', 'condition', 'is_repairable', 'category', 'created_at')
    search_fields = ('title', 'description', 'pickup_location', 'donor__username')
    list_editable = ('status', 'moderation_status')
    actions = ['approve_items', 'mark_as_given']

    def approve_items(self, request, queryset):
        queryset.update(moderation_status='APPROVED')
    approve_items.short_description = "Approve selected items"

    def mark_as_given(self, request, queryset):
        queryset.update(status='GIVEN_AWAY')
    mark_as_given.short_description = "Mark selected items as Given Away"


@admin.register(ItemRequest)
class ItemRequestAdmin(admin.ModelAdmin):
    list_display = ('item', 'requester', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('item__title', 'requester__username', 'message')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'item', 'reported_user', 'reported_by', 'reason', 'status', 'created_at')
    list_filter = ('status', 'reason', 'created_at')
    search_fields = ('item__title', 'reported_user__username', 'reported_by__username', 'details')


@admin.register(SupportInquiry)
class SupportInquiryAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'user', 'email', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('subject', 'message', 'user__username', 'email')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('email', 'user', 'code', 'purpose', 'is_used', 'attempts', 'created_at', 'expires_at')
    list_filter = ('purpose', 'is_used', 'created_at')
    search_fields = ('email', 'user__username', 'code')
    readonly_fields = ('code', 'created_at')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'location', 'phone', 'is_verified', 'email_verified', 'created_at')
    list_filter = ('is_verified', 'email_verified', 'created_at')
    search_fields = ('user__username', 'user__email', 'location')
