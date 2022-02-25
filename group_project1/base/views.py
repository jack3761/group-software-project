from asyncio.windows_events import NULL
from email import message

from ipaddress import ip_address

from http.client import responses

import re
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from .forms import ChallengeForm, UserRegisterForm, ResponseForm,ProfileForm
from .models import Category, Challenges, Responses, Profile
from django.db.models import Q
from django.urls import reverse_lazy,reverse
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib import messages
import folium, json
from axes.models import AccessAttempt
from .models import AccessAttemptAddons
import datetime

def add_location(map, location, popup):
    #tooltip
    tooltip = 'Click for more info'
    folium.Marker(location, popup, tooltip=tooltip).add_to(map)
    return map

# Function to open and return a json file 
def open_json_file(file_name):
    file = open(file_name)
    return json.load(file)


# View for the main homepage
def home(request):

    # Map is centred at this location
    center = [50.735805, -3.533051]

    # Map that is bounded to Exeter Uni
    map = folium.Map(location = center,
                 min_lon=-3.520532,
                 max_lon=-3.548116,
                 min_lat=50.729748,
                 max_lat=50.741780,
                 max_bounds=True,
                 zoom_start = 16,
                 min_zoom = 15)

    # Select all categories
    categories = Category.objects.all()

    # Get the filter from the ?q= in the URL
    q = request.GET.get('q') if request.GET.get('q') != None else ''

    # Get all challenges, not done by the current user

    if request.user.is_authenticated:
        responses = Responses.objects.filter(user = request.user).values_list('challenge_id')

        challenges = Challenges.objects.exclude(id__in=responses).filter(Q(
            category__name__icontains=q)).order_by('-created')
   
        
        #locations = open_json_file('base/resources/latLong.json')
        #print(locations)
        # Adds markers to the map for each location
        for challenge in challenges:
            coords = [challenge.lat, challenge.long]
            popup = challenge.name
            map = add_location(map, coords, popup)

    else:
         challenges = Challenges.objects.all().order_by('-created')
         for challenge in challenges:
            coords = [challenge.lat, challenge.long]
            popup = challenge.name
            map = add_location(map, coords, popup)
        

    map = map._repr_html_()

    # Variables to pass to the database
    context = {'categories':categories,'challenges':challenges, 'map':map}

    return render(request,'base/home.html',context)


# View for logging in
def loginPage(request):

    # Allows us to change the page based on if a user is logged in
    page = 'login'
    if request.user.is_authenticated:
        return redirect('home')


    # Get info from html form
    if request.method == 'POST':
        username = request.POST.get('username').lower()
        password = request.POST.get('password')

        try:
            user = User.objects.get(username=username)
        except:
            messages.error(request, 'User does not exist')
            
        user = authenticate(request, username=username, password=password)

        if user is not None:
            user.backend = 'django.contrib.auth.backends.ModelBackend' # Sets the backend authenticaion model
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Username or password does not exist')

    
    context = {'page':page}
    return render(request, 'base/login_register.html', context)


# Logout usef
def logoutUser(request):

    logout(request)
    return redirect('home')


# User registration
def registerPage(request):
    
    # Getting form from forms.py
    form = UserRegisterForm()


    if request.method == 'POST':
        form = UserRegisterForm(request.POST)

        # Save form if it is valid
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')

            user.backend = 'django.contrib.auth.backends.ModelBackend' # Sets the backend authenticaion model

            Profile.objects.create(
                user = user,
                name = user.username
            )

            login(request,user)
            messages.success(request, f'Account created for {username}!')
            return redirect('home')



    context = {'form': form}
    return render(request, 'base/login_register.html',context)


# Only let a user see profile if logged in
@login_required(login_url='/login')
def userProfile(request):
    return render(request, 'base/profile.html',{})


# Create challenge
def createChallenge(request):
    form = ChallengeForm()
    if request.method == 'POST':
        form = ChallengeForm(request.POST)

        # If valid challenge, add to database
        if form.is_valid():
            form.save()
            return redirect('home')
    context = {'form':form}
    return render(request,'base/createChallenge.html',context)

@login_required(login_url='/login')
def createResponse(request,pk):
    challenge = Challenges.objects.get(id=pk)
    form = ResponseForm()
    if request.method == 'POST':
        form = ResponseForm(request.POST)

        #If valid response, add to database
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.challenge = challenge

            obj.save()
            profile = request.user.profile
            profile.points += challenge.points
            profile.save()
            return redirect('home')
    context = {'form':form}
    return render(request,'base/createResponse.html',context)


# Converts timedelta object into a readable string
def strfdelta_round(tdelta, round_period='second'):
  """timedelta to string,  use for measure running time
  attend period from days downto smaller period, round to minimum period
  omit zero value period  
  """
  period_names = ('day', 'hour', 'minute', 'second', 'millisecond')
  if round_period not in period_names:
    raise Exception(f'round_period "{round_period}" invalid, should be one of {",".join(period_names)}')
  period_seconds = (86400, 3600, 60, 1, 1/pow(10,3))
  period_desc = ('days', 'hours', 'minutes', 'seconds', 'msecs')
  round_i = period_names.index(round_period)
  
  string = ''
  remainder = tdelta.total_seconds()
  for i in range(len(period_names)):
    q, remainder = divmod(remainder, period_seconds[i])
    if int(q)>0:
      if not len(string)==0:
        string += ' '
      string += f'{q:.0f} {period_desc[i]}'
    if i==round_i:
      break
    if i==round_i+1:
      string += f'{remainder} {period_desc[round_i]}'
      break
    
  return string

# When user is locked out add message and redirect to home page
def lockout(request, credentials, *args, **kwargs):
    try:
        username = request.POST.get("username")
        ip_address = request.axes_ip_address
        account = AccessAttempt.objects.filter(username=username).filter(ip_address=ip_address)
        current_time = datetime.datetime.now()
        timeout = 5 # In minutes
        result = AccessAttempt.objects.raw(
                '''
                SELECT axes_accessattempt.id, base_accessattemptaddons.expiration_date
                FROM axes_accessattempt
                INNER JOIN base_accessattemptaddons
                ON axes_accessattempt.id = base_accessattemptaddons.accessattempt_id
                WHERE axes_accessattempt.username = %s and axes_accessattempt.ip_address = %s
                ''', [username, ip_address]
            )[0]

        # Check if the user still has to wait to login again
        if (current_time < result.expiration_date):
            time = result.expiration_date - current_time
            time_s = strfdelta_round(time)
            messages.warning(request, (f"Locked out for {time_s} due to too many login failures"))
        else:
            # Delete the user from the timeout model and re-request the login
            account.delete()
            return loginPage(request)

    except IndexError:
        expiration_date = current_time + datetime.timedelta(minutes=timeout)
        id = AccessAttempt.objects.filter(username=username, ip_address=ip_address)[0].id
        addons = AccessAttemptAddons(expiration_date=expiration_date, accessattempt_id=id)
        messages.warning(request, (f"Locked out for {timeout} minutes due to too many login failures"))
        addons.save()

    return redirect('login')


@login_required(login_url='/login')
def myResponses(request):
    responses = Responses.objects.filter(user=request.user).order_by('-created')
    context = {'responses':responses}
    return render(request,'base/myResponses.html',context)