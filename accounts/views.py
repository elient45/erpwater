from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from .forms import LoginForm, UserCreateForm
from .models import UserProfile


def is_admin_user(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return hasattr(user, "profile") and user.profile.role == UserProfile.ROLE_ADMIN


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Connexion réussie.")
            return redirect("dashboard")
        messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")

    return render(request, "accounts/login.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Déconnexion réussie.")
    return redirect("accounts:login")


@login_required
@user_passes_test(is_admin_user)
def user_list(request):
    users = User.objects.select_related("profile").all().order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})


@login_required
@user_passes_test(is_admin_user)
def user_create(request):
    form = UserCreateForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_password(form.cleaned_data["password"])
        user.save()

        UserProfile.objects.create(
            user=user,
            phone=form.cleaned_data.get("phone"),
            role=form.cleaned_data["role"],
        )

        messages.success(request, "Utilisateur créé avec succès.")
        return redirect("accounts:user_list")

    return render(request, "accounts/user_form.html", {"form": form, "title": "Nouvel utilisateur"})