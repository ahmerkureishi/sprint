#!/usr/bin/env python
#
# Copyright 2008 Todd A. Webb
#

"""A collaborative Scrum management application built on Google App Engine."""

__author__ = 'Todd Webb'

import os
import cgi
import datetime
import logging

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext import db

import wsgiref.handlers

# Set to true if we want to have our webapp print stack traces, etc
_DEBUG = True

class BaseRequestHandler(webapp.RequestHandler):
	"""Supplies a common template generation function.

	When you call generate(), we augment the template variables supplied with
	the current user in the 'user' variable and the current webapp request
	in the 'request' variable.

	Adapted from tasks.py by Bret Taylor, Google, Inc. under the Apache License 
	version 2.0.
	"""
	def generate(self, template_name, template_values={}):
		teams_query = TeamMember.gql("WHERE user = :1", users.GetCurrentUser())
		teams = [team_member for team_member in teams_query.fetch(20)]
		for team_member in teams:
			team_member.owner_app_user = team_member.team.get_owner()
		values = {
			'request': self.request,
			'user': AppUser.getCurrentUser(),
			'teams': teams,
			'today': datetime.date.today(),
			'login_url': users.CreateLoginURL(self.request.uri),
			'logout_url': users.CreateLogoutURL('http://' + self.request.host + '/'),
			'debug': self.request.get('deb'),
			'application_name': 'Sprint',
		}
		values.update(template_values)
		directory = os.path.dirname(__file__)
		path = os.path.join(directory, os.path.join('templates', template_name))
		self.response.out.write(template.render(path, values, debug=_DEBUG))


class MainPage(BaseRequestHandler):
	def get(self):
		'''Displays the dashboard page.'''
		# Make sure we have an AppUser session object otherwise send to the user profile to make one
		user = users.get_current_user()
		if not AppUser.getFromUser(user):
			self.redirect('/user')
			return
		else:
			app_user = AppUser.getFromUser(user)
		
		# Get all the user's items and the associated sprints and projects. This is sort of inefficient
		# because it gets all projects and sprints then removes the ones that aren't related to user items
		project_query = Project.gql("WHERE team = :1 ORDER BY title", AppUser.getCurrentUser().current_team)
		projects = project_query.fetch(200)
		user_projects = [project for project in projects]
		for project in user_projects:
			sprint_query = db.GqlQuery("SELECT * FROM Sprint WHERE project = :1 ORDER BY start_date ASC", project)
			project.sprints = [sprint for sprint in sprint_query]
			for sprint in project.sprints:
				item_query = db.GqlQuery("SELECT * FROM Item \
					WHERE sprint = :1 AND backlog = :2 AND owner = :3 ORDER BY title", sprint, None, AppUser.getCurrentUser())
				sprint.items = [item for item in item_query]
			for sprint in project.sprints[:]:
				if not sprint.items:
					project.sprints.remove(sprint)
		for project in user_projects[:]:
			if not project.sprints:
				user_projects.remove(project)

		backlog_query = Backlog.gql("WHERE team = :1 ORDER BY title", AppUser.getCurrentUser().current_team)
		backlogs = backlog_query.fetch(200)

		alert = app_user.alert_message
		alert_type = app_user.alert_type
		app_user.alert_message = None
		app_user.put()

		self.generate('mainpage.html', {
			'user_projects': user_projects,
			'projects': projects,
			'backlogs': backlogs,
			'users': AppUser.getCurrentUser().current_team.get_all_members(),
			'alert': alert,
			'alert_type': alert_type,
			})


class UserPage(BaseRequestHandler):
	def get(self):
		'''Displays the user profile page.'''
		# Make sure the user has an AppUser profile, if not, create one and a team and a team member relationship
		app_user = AppUser.getCurrentUser()
		if not app_user:
			# Create a new Team
			team = Team()
			team.put()
			# Create a new AppUser record
			app_user = AppUser()
			app_user.user = users.GetCurrentUser()
			app_user.current_team = team
			app_user.alert_message = "Please update your profile."
			app_user.alert_type = "success"
			app_user.put()
			# Create an owner relationship between the Team and the AppUser
			team_member = TeamMember(user=users.GetCurrentUser(),owner=True,team=app_user.current_team)
			team_member.put()
			team_members = [team_member,]
		else:
			team_member_query = TeamMember.gql('WHERE user = :1 AND owner = True', users.GetCurrentUser())
			team_member = team_member_query.get()
			team = team_member.team
			team_member_query_2 = TeamMember.gql('WHERE team = :1', team)
			team_members = [AppUser.getFromUser(team_member.user) for team_member in team_member_query_2.fetch(100)]

		alert = app_user.alert_message
		alert_type = app_user.alert_type
		app_user.alert_message = None
		app_user.put()
		
		self.generate('userpage.html', {
			'team': team,
			'team_members': team_members,
			'alert': alert,
			'alert_type': alert_type,
			})


class ProjectPage(BaseRequestHandler):
	'''Displays the project page.'''
	def get(self):
		id = self.request.get('id')
		project = Project.get(id)
		sprint_query = db.GqlQuery("SELECT * FROM Sprint WHERE project = :1 ORDER BY start_date ASC", project)
		project.sprints = [sprint for sprint in sprint_query]
		for sprint in project.sprints:
			item_query = db.GqlQuery("SELECT * FROM Item WHERE sprint = :1 AND backlog = :2 ORDER BY title", sprint, None)
			sprint.items = [item for item in item_query]
			backlog_item_query = db.GqlQuery("SELECT * FROM Item WHERE sprint = :1 AND backlog > :2 ORDER BY backlog, title", sprint, 0)
			sprint.backlog_items = [item for item in backlog_item_query]
			today = datetime.date.today()
			query_datetime = datetime.datetime.combine(today,datetime.time().min)
			snap_query = db.GqlQuery("SELECT * FROM SprintSnap WHERE sprint = :1 AND date <= :2 ORDER BY date", sprint, query_datetime)
			if snap_query.count():
				snapshots = snap_query.fetch(200,0)
				sprint.snap = snapshots[-1]
				#Build chart data
				remaining_days = (sprint.end_date - sprint.snap.date).days
				remaining_series = ",-1" * (remaining_days - 1) + ",0"
				estimates = [int(snap.estimate) for snap in snapshots]
				sprint.chart_start_date = snapshots[0].date
				sprint.chart_end_date = sprint.end_date
				sprint.chart_total_data_points = len(estimates) + remaining_days - 1
				sprint.chart_data = ",".join(str(estimate) for estimate in estimates) + remaining_series
				sprint.chart_limits = "0," + str(max(estimates))
		
		app_user = AppUser.getCurrentUser()
		alert = app_user.alert_message
		alert_type = app_user.alert_type
		app_user.alert_message = None
		app_user.put()
	
		self.generate('projectpage.html', {
			'project': project, 
			'users': AppUser.getCurrentUser().current_team.get_all_members(),
			'alert': alert,
			'alert_type': alert_type,
		})


class BacklogPage(BaseRequestHandler):
	'''Displays the backlog page.'''
	def get(self):
		id = self.request.get('id')
		backlog = Backlog.get(id)
		items = db.GqlQuery("SELECT * FROM Item WHERE backlog = :1 ORDER BY title", backlog)
		
		project_query = Project.gql("WHERE team = :1 ORDER BY title", AppUser.getCurrentUser().current_team)
		projects = project_query.fetch(200)
		user_projects = [project for project in projects]
		sprints = []
		for project in user_projects:
			sprint_query = db.GqlQuery("SELECT * FROM Sprint WHERE project = :1 ORDER BY start_date ASC", project)
			result = [sprint for sprint in sprint_query]
			sprints.extend(result)

		self.generate('backlogpage.html', {
			'backlog': backlog, 
			'items': items, 
			'users': AppUser.getCurrentUser().current_team.get_all_members(),
			'sprints': sprints,
		})


class ItemPage(BaseRequestHandler):
	'''Displays the item page.'''
	def get(self):
		id = self.request.get('id')
		item = Item.get(id)
		next = self.request.get('next')

		self.generate('itempage.html', {
			'item': item,
			'next': next,
			'users': AppUser.getCurrentUser().current_team.get_all_members(),
		})


class HelpPage(BaseRequestHandler):
	'''Displays the help page.'''
	def get(self):
		self.generate('helppage.html', {});


class UpdateUserAction(BaseRequestHandler):
	def post(self):
		'''Edits the user profile.'''
		id = self.request.get('id')
		user = AppUser.get(id)

		user.first_name = self.request.get('first_name')
		user.last_name = self.request.get('last_name')
		user.alert_message = "You have successfully updated your profile."
		user.alert_type = "success"

		team_member_query = TeamMember.gql('WHERE user = :1 AND owner = True', users.GetCurrentUser())
		team_member = team_member_query.get()
		team = team_member.team
		team.title = self.request.get('team_title')

		user.put()
		team.put()

		self.redirect('/user')


class CreateProjectAction(BaseRequestHandler):
	def post(self):
		project = Project(team=AppUser.getCurrentUser().current_team)
		project.title = self.request.get('title')
		
		project.put()
		
		self.redirect('/')


class CreateSprintAction(BaseRequestHandler):
	def post(self):
		app_user = AppUser.getCurrentUser()
		title = self.request.get('title')
		project = Project.get(self.request.get('project_id'))
		start = self.request.get('start_date').split('/')
		end = self.request.get('end_date').split('/')
		start_date = datetime.date(int(start[2]), int(start[0]), int(start[1]))
		end_date = datetime.date(int(end[2]), int(end[0]), int(end[1]))
		if start_date >= end_date:
			app_user.alert_message = "The start date must be earlier than the end date."
			app_user.alert_type = "error"
			app_user.put()
		else:
			sprint = Sprint()
			sprint.title = title
			sprint.project = Project.get(self.request.get('project_id'))
			sprint.start_date = start_date
			sprint.end_date = end_date
			sprint.put()
		
		self.redirect(self.request.get('next'))


class CreateBacklogAction(BaseRequestHandler):
	def post(self):
		backlog = Backlog(team=AppUser.getCurrentUser().current_team)
		backlog.title = self.request.get('title')
		backlog.owner = AppUser.get(self.request.get('owner'))
		
		backlog.put()
		
		self.redirect('/')


class DeleteItemAction(BaseRequestHandler):
	def post(self):
		item_key = self.request.get('id')
		item = Item.get(item_key)
		delta = 0 - item.estimate
		if not item.backlog:
			item.sprint.update_snapshot(delta)
		item.delete()
		
		self.redirect(self.request.get('next'))


class SetCurrentTeamAction(BaseRequestHandler):
	def post(self):
		app_user = AppUser.getCurrentUser()
		team = Team.get(self.request.get('team'))
		if team.current_user_has_access():
			app_user.current_team = team
			app_user.alert_message = "You changed your current team to: " + team.title
			app_user.alert_type = "success"
			app_user.put()
			self.redirect('/')
		else:
			self.error(403)
			return


class AddMemberAction(BaseRequestHandler):
  def post(self):
	team = Team.get(self.request.get('team'))
	email = self.request.get('email')
	if not team or not email:
	  self.error(403)
	  return

	# Validate this user is the owner of this team
	if not team.current_user_is_owner():
	  self.error(403)
	  return

	user = users.User(email)
	if not team.user_has_access(user):
	  member = TeamMember(user=user, team=team)
	  member.put()
	self.redirect('/user')


class EditItemAction(BaseRequestHandler):
	def post(self):
		item_key = self.request.get('id')
		
		if item_key:
			item = Item.get(item_key)
			new_item = False
		else:
			item = Item(title = " ")
			new_item = True
		
		if self.request.get('title'):
			item.title = self.request.get('title')
		
		if item.backlog:
			backlog_item = True
		elif self.request.get('backlog_id'):
			item.backlog = Backlog.get(self.request.get('backlog_id'))
			backlog_item = True
		else:
			backlog_item = False
		
		if self.request.get('sprint_id'):
			item.sprint = Sprint.get(self.request.get('sprint_id'))
		
		if self.request.get('owner'):
			if self.request.get('owner') == "none":
				item.owner = None
			else:
				item.owner = AppUser.get(self.request.get('owner'))
		
		if self.request.get('estimate'):
			if item.estimate != int(self.request.get('estimate')):
				if not new_item:
					previous_estimate = item.estimate
				else:
					previous_estimate = 0
				item.estimate = int(self.request.get('estimate'))
				delta = item.estimate - previous_estimate
				
				today = datetime.date.today()
				item.last_estimate_date = today
				item.last_estimate_by = AppUser.getCurrentUser()
				
				if not backlog_item:
					item.sprint.update_snapshot(delta)
		
		item.put()
		
		next = self.request.get('next')
		if next:
			self.redirect(self.request.get('next'))
		elif item.backlog:
			backlog_id = str(item.backlog.key())
			self.redirect('/backlog?id=' + backlog_id )
		elif item.sprint:
			project_id = str(item.sprint.project.key())
			self.redirect('/project?id=' + project_id )
		else:
			self.redirect('/')


class Team(db.Model):
	'''Represents a Team.

	A Team owns a set of backlogs and projects. For now a user can only own one team but can be
	a member of more than one team (see TeamMember).'''
	title = db.StringProperty(default="My Team")
	
	def get_all_members(self):
		query = db.GqlQuery("SELECT * FROM TeamMember WHERE team = :1", self)
		result =  query.fetch(100)
		return [AppUser.getFromUser(team_member.user) for team_member in result]
	
	def get_owner(self):
		query = db.GqlQuery("SELECT * FROM TeamMember WHERE team = :1 AND owner = True", self)
		result =  query.get()
		return AppUser.getFromUser(result.user)
	
	def current_user_is_owner(self):
		user = AppUser.getCurrentUser().user
		query = db.GqlQuery("SELECT * FROM TeamMember WHERE team = :1 AND user = :2 AND owner = True", self, user)
		return query.get()
	
	def current_user_has_access(self):
		return self.user_has_access(users.GetCurrentUser())
		
	def user_has_access(self, user):
		if not user: return False
		query = db.GqlQuery("SELECT * FROM TeamMember WHERE team = :1 AND user = :2", self, user)
		return query.get()


class AppUser(db.Model):
	user = db.UserProperty()
	first_name = db.StringProperty(default="First")
	last_name = db.StringProperty(default="Last")
	alert_message = db.StringProperty()
	alert_type = db.StringProperty()
	current_team = db.ReferenceProperty(Team)
	
	@staticmethod
	def getCurrentUser():
		"""docstring for getCurrent"""
		user = users.GetCurrentUser()
		return AppUser.getFromUser(user)
	
	@staticmethod
	def getFromUser(user):
		query = AppUser.gql("WHERE user = :1", user)
		return query.get()


class TeamMember(db.Model):
	'''Represents the many-to-many relationship between AppUsers and Teams.

	Serves as ACL to Team data. Projects and Backlogs are connected to only one team.'''
	user = db.UserProperty(required=True)
	owner = db.BooleanProperty(default=False)
	team = db.ReferenceProperty(Team, required=True)


class Project(db.Model):
	title = db.StringProperty()
	team = db.ReferenceProperty(Team, required=True)


class Sprint(db.Model):
	title = db.StringProperty()
	project = db.ReferenceProperty(Project)
	start_date = db.DateProperty()
	end_date = db.DateProperty()
	
	def get_current_snapshot(self):
		today = datetime.date.today()
		query_datetime = datetime.datetime.combine(today,datetime.time().min)
		snap_query = SprintSnap.gql("WHERE sprint = :1 AND date <= :2 ORDER BY date DESC", self, query_datetime)
		return snap_query.get()
	
	def update_snapshot(self, delta):
		today = datetime.date.today()
		query_datetime = datetime.datetime.combine(today,datetime.time().min)
		snap_query = SprintSnap.gql("WHERE sprint = :1 AND date = :2", self, query_datetime)
		snap = snap_query.get()
		if snap:
			snap.estimate += delta
			snap.put()
		else:
			snap_query = SprintSnap.gql("WHERE sprint = :1 AND date < :2 ORDER BY date DESC", self, query_datetime)
			snap = snap_query.get()
			if snap:
				todays_estimate = snap.estimate + delta
			else:
				todays_estimate = delta
			snap = SprintSnap(sprint=self, estimate=todays_estimate)
			snap.put()


class SprintSnap(db.Model):
	sprint = db.ReferenceProperty(Sprint)
	date = db.DateProperty(auto_now_add=True)
	estimate = db.IntegerProperty(default=0)


class Backlog(db.Model):
	title = db.StringProperty()
	owner = db.ReferenceProperty(AppUser)
	team = db.ReferenceProperty(Team, required=True)


class Item(db.Model):
	title = db.StringProperty(required=True)
	backlog = db.ReferenceProperty(Backlog, default=None)
	sprint = db.ReferenceProperty(Sprint, default=None)
	owner = db.ReferenceProperty(AppUser, default=None)
	estimate = db.IntegerProperty(default=0)
	last_estimate_date = db.DateProperty(auto_now_add=True)
	last_estimate_by = db.ReferenceProperty(AppUser, default=None, collection_name='estimator_set')


def main():
	apps_binding = []

	apps_binding.append(('/', MainPage))
	apps_binding.append(('/user', UserPage))
	apps_binding.append(('/project', ProjectPage))
	apps_binding.append(('/backlog', BacklogPage))
	apps_binding.append(('/item', ItemPage))
	apps_binding.append(('/user/update', UpdateUserAction))
	apps_binding.append(('/project/new', CreateProjectAction))
	apps_binding.append(('/sprint/new', CreateSprintAction))
	apps_binding.append(('/backlog/new', CreateBacklogAction))
	apps_binding.append(('/item/new', EditItemAction))
	apps_binding.append(('/item/update', EditItemAction))
	apps_binding.append(('/help', HelpPage))
	apps_binding.append(('/team/set-current', SetCurrentTeamAction))
	apps_binding.append(('/team/add-member', AddMemberAction))
	apps_binding.append(('/item/delete', DeleteItemAction))

	application = webapp.WSGIApplication(apps_binding, debug=_DEBUG)
	wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
   main()
