from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from .forms import LoginForm

# Hardcoded credentials
HARDCODED_EMAIL = 'info@ulendolodge.com'
HARDCODED_PASSWORD = 'Ulendo@#2025!'


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Simple hardcoded login view."""
    if request.user.is_authenticated:
        return redirect('reservations:dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            # Check hardcoded credentials
            if email == HARDCODED_EMAIL and password == HARDCODED_PASSWORD:
                # Create a simple user session
                from django.contrib.auth.models import User
                user, created = User.objects.get_or_create(
                    username=email,
                    defaults={'email': email, 'is_staff': False}
                )
                login(request, user)
                messages.success(request, 'Welcome to Ulendo Reservation System!')
                return redirect('reservations:dashboard')
            else:
                messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    """Logout view."""
    from django.contrib.auth import logout
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('accounts:login')
