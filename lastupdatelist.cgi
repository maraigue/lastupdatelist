#!/usr/bin/env ruby
# -*- coding: utf-8 -*-

require 'cgi'
require 'cgi/session'
require 'yaml'
require 'sqlite3'
require 'digest/sha2'

# ============================================================
# Modify if needed
# ============================================================
load './language.en.cgi'
DB_FILE_NAME = 'lastupdatelist.sqlite3.cgi'
SESSION_DURATION = 2592000 # How long the log-in session is kept, in seconds

# ============================================================
# Other options: do not modify unless you clear the database
# ============================================================
SALT_LENGTH = 128

# ============================================================
# Main class
# ============================================================
class LastUpdate
  # ============================================================
  # Helper functions
  # ============================================================
  def self.setup_db_defs(db_def)
    db_def[:key_ids] = Hash[*db_def[:keys].map(&:first).each_with_index.to_a.flatten]
    db_def[:sql] = "CREATE TABLE #{db_def[:name]}("+db_def[:keys].map{ |k| k[0]+' '+k[1] }.join(', ')+")"
  end

  def hash_password(pass, salt = SALT_LENGTH.times.map{ rand(0x20..0x7E) }.pack("C*"))
    salt + Digest::SHA512.digest("#{salt}#{pass}")
  end

  def check_password(pass, hash)
    salt = hash[0...SALT_LENGTH]
    hash_password(pass, salt) == hash
  end

  # ============================================================
  # Definitions of tables
  # ============================================================
  
  # Table for storing users
  @@TABLE_USERS = {
    :name => 'users',
    :keys => [
        ['id', 'integer primary key autoincrement not null', nil],
        ['name', 'text not null', ''],
        ['pass', 'text not null', ''],
    ],
  }
  setup_db_defs @@TABLE_USERS
  
  # Table for storing tasks
  @@TABLE_TASKS = {
    :name => 'tasks',
    :keys => [
        ['id', 'integer primary key autoincrement not null', nil],
        ['sort_order', 'integer not null', 0],
        ['name', 'text not null', ''],
        ['date1', 'integer not null', 0],
        ['date2', 'integer not null', 0],
    ],
  }
  setup_db_defs @@TABLE_TASKS
  
  # ============================================================
  # Database operations
  # ============================================================
  def add_task(name)
    @db.transaction do
      current_newest = @db.execute("SELECT MAX(sort_order) FROM #{@@TABLE_TASKS[:name]}").first.first
      newest = (current_newest ? current_newest+1 : 0)
      
      values = @@TABLE_TASKS[:keys].map{ |k| k[0] == 'name' ? name : (k[0] == 'sort_order' ? newest : k[2]) }
      placeholder = '?, ' * (@@TABLE_TASKS[:keys].size - 1) + '?'
      sql = "INSERT INTO #{@@TABLE_TASKS[:name]} VALUES(#{placeholder})"
      
      @db.execute(sql, values)
    end
  end
  
  def conduct_task(task_id)
    task_id = task_id.to_i
    @db.transaction do
      result = @db.execute("SELECT * FROM #{@@TABLE_TASKS[:name]} WHERE id = ?", task_id)
      if result.size != 1
        @errormsg << ERROR_TASK_NOT_FOUND
        return
      end
      
      @db.execute("UPDATE #{@@TABLE_TASKS[:name]} SET date1 = ?, date2 = ? where id = ?", [Time.now.to_i, result.first[@@TABLE_TASKS[:key_ids]['date1']], task_id])
    end
  end
  
  def edit_task(task_id, name)
    if name =~ /\A(\s|　)*\z/
      @errormsg << REQUEST_REJECTION_EMPTY_TASK_NAME
      return
    end
    
    if @db.execute("SELECT * FROM #{@@TABLE_TASKS[:name]} WHERE id = ?", [task_id]).empty?
      @errormsg << ERROR_TASK_NOT_FOUND
      return
    end
    
    @db.execute("UPDATE #{@@TABLE_TASKS[:name]} SET name = ? WHERE id = ?", [name, task_id])
    @errormsg << NOTIFICATION_TASK_NAME_CHANGED
  end
  
  def delete_task(task_id)
    if @db.execute("SELECT * FROM #{@@TABLE_TASKS[:name]} WHERE id = ?", [task_id]).empty?
      @errormsg << ERROR_TASK_NOT_FOUND
    else
      @db.execute("DELETE FROM #{@@TABLE_TASKS[:name]} WHERE id = ?", [task_id])
      if @db.execute("SELECT * FROM #{@@TABLE_TASKS[:name]} WHERE id = ?", [task_id]).empty?
        @errormsg << NOTIFICATION_TASK_DELETED
      else
        @errormsg << ERROR_TASK_CANNOT_BE_DELETED
      end
    end
  end
  
  def add_user(name, pass, pass2)
    if name.empty?
      @errormsg << REQUEST_REJECTION_EMPTY_USER_NAME
    end
    if pass.empty? || pass2.empty?
      @errormsg << REQUEST_REJECTION_EMPTY_PASSWORD
    elsif pass != pass2
      @errormsg << REQUEST_REJECTION_PASSWORD_UNMATCHED
    end
    
    return unless @errormsg.empty?
    
    @db.transaction do
      result = @db.execute("SELECT * FROM #{@@TABLE_USERS[:name]}")
      
      unless result.empty?
        @errormsg << REQUEST_REJECTION_USER_ALREADY_EXISTS
      else
        @db.execute("INSERT INTO #{@@TABLE_USERS[:name]} VALUES(?, ?, ?)", [0, name, hash_password(pass)])
      end
    end
  end
  
  # ============================================================
  # Helper functions for display
  # ============================================================
  def header
    puts @cgi.header
    puts <<HTML
<html>
<head>
<meta http-equiv="content-type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width">
<title>Last Update List</title>
<style type="text/css"><!--
.conductbutton{ display: inline; }
.conductbutton p{ display: inline; }
.conduct{ font-size: 125%; margin: 0.25em 0em; }
#maintable td, #maintable th{ border-bottom: 1px solid black }
--></style>
</head>
<body>
<h1>Last Update List</h1>
HTML
  end
  
  def footer
    puts <<HTML
<hr>
<address>"Last Update List" by <a href="http://hhiro.net/">H.Hiro</a> (<a href="https://github.com/maraigue/lastupdatelist">github</a>)</address>
</body>
</html>
HTML
  end
  
  def time_diff_summary(t)
    now = Time.now
    n = now - t
    if n < 60
      UI_SECONDS_AGO % [n.to_i]
    elsif n < 3600
      UI_MINUTES_AGO % [(n/60).to_i]
    elsif n < 86400
      UI_HOURS_AGO % [(n/3600).to_i]
    else
      UI_DAYS_AND_HOURS_AGO % [(n/86400).to_i, ((n%86400)/3600).to_i]
    end
  end
  
  def datestr(i)
    if i <= 0
      ''
    else
      t = Time.at(i)
      t.strftime("%y-%m-%d (%a) %T<br><small>(#{time_diff_summary(t)})</small>")
    end
  end
  
  # ============================================================
  # Displays for POST method
  # ============================================================
  def action_no_user_post
    begin
      case @cgi['action']
      when 'add_user'
        add_user(@cgi['name'], @cgi['pass'], @cgi['pass2'])
      else
        # Do nothing
      end
    rescue Exception => e
      @errormsg << "#{ERROR_FAILED_ACTION} - #{@cgi['action']} (#{e.class}: #{e})\n#{e.backtrace.join("\n")}"
    end
    
    @session['errormsg'] = @errormsg.map{ |e| CGI.escape(e) }.join("\n")
    puts @cgi.header({
      "status" => "REDIRECT",
      "Location" => "./#{File.basename(__FILE__)}"
    })
  end
  
  def action_login_post
    begin
      case @cgi['action']
      when 'login'
        # Retrieve the registered user
        users = @db.execute("SELECT pass FROM #{@@TABLE_USERS[:name]} WHERE name LIKE ?", [@cgi['name']])
        if users.size != 1
          @errormsg << REQUEST_REJECTION_INVALID_USER_OR_PASSWORD
        else
          if check_password(@cgi['pass'], users.first.first)
            @session['login'] = @cgi['name']
STDERR.puts "LOGIN"
          else
            @errormsg << REQUEST_REJECTION_INVALID_USER_OR_PASSWORD
          end
        end
      else
        # Do nothing
      end
    rescue Exception => e
      @errormsg << "#{ERROR_FAILED_ACTION} - #{@cgi['action']} (#{e.class}: #{e})\n#{e.backtrace.join("\n")}"
    end
    
    @session['errormsg'] = @errormsg.map{ |e| CGI.escape(e) }.join("\n")
    puts @cgi.header({
      "status" => "REDIRECT",
      "Location" => "./#{File.basename(__FILE__)}"
    })
  end
  
  def action_main_post
    begin
      case @cgi['action']
      when 'delete_task'
        delete_task(@cgi['task_id'])
      when 'add_task'
        add_task(@cgi['name'])
      when 'edit_task'
        edit_task(@cgi['task_id'], @cgi['name'])
      when 'conduct_task'
        conduct_task(@cgi['task_id'])
      when 'logout'
        @session['login'] = ''
STDERR.puts "LOGOUT"
        @errormsg << UI_LOGGED_OUT
      else
        # Do nothing
      end
    rescue Exception => e
      @errormsg << "#{ERROR_FAILED_ACTION} - #{@cgi['action']} (#{e.class}: #{e})\n#{e.backtrace.join("\n")}"
    end
    
    @session['errormsg'] = @errormsg.map{ |e| CGI.escape(e) }.join("\n")
    puts @cgi.header({
      "status" => "REDIRECT",
      "Location" => "./#{File.basename(__FILE__)}"
    })
  end
  
  # ============================================================
  # Displays for GET method
  # ============================================================
  def display_errormsg
    unless @errormsg.empty?
      puts "<div style=\"background:#ffcccc; border: 1px solid #990000\">"
      @errormsg.each do |e|
        puts "<p>" + e.split("\n").map{ |s| CGI.escapeHTML(s) }.join('<br>')+"</p>"
      end
      puts "</div>"
    end
  end
  
  def action_main_get
    header
    display_errormsg
    
    # Forms for edition/deletion
    if @cgi['editform']
      edit_target = @db.execute("SELECT * FROM #{@@TABLE_TASKS[:name]} where id = ?", [@cgi['editform'].to_i]).first
      if edit_target
        print <<HTML
<div style="background:#ffffcc; border: 1px solid #999900">
<p>#{UI_TASK} "#{CGI.escapeHTML(edit_target[@@TABLE_TASKS[:key_ids]['name']])}":</p>
<form method="POST" action="#{File.basename(__FILE__)}"><p>
<input type="hidden" name="action" value="edit_task">
<input type="hidden" name="task_id" value="#{CGI.escapeHTML(edit_target[@@TABLE_TASKS[:key_ids]['id']].to_s)}">
#{UI_NEW_TASK_NAME}
<input type="text" autocomplete="off" name="name" value="#{CGI.escapeHTML(edit_target[@@TABLE_TASKS[:key_ids]['name']])}">
<input type="submit" value="#{UI_BUTTON_UPDATE_TASK_NAME}">
</p></form>
<form method="POST" action="#{File.basename(__FILE__)}" onsubmit="javascript:return confirm('#{UI_CONFIRMING_DELETING_TASK} - '+#{CGI.escapeHTML(edit_target[@@TABLE_TASKS[:key_ids]['name']].inspect)})"><p>
<input type="hidden" name="action" value="delete_task">
<input type="hidden" name="task_id" value="#{CGI.escapeHTML(edit_target[@@TABLE_TASKS[:key_ids]['id']].to_s)}">
<input type="submit" value="#{UI_BUTTON_DELETE_TASK_NAME}">
</p></form>
</div>
HTML
      end
    end
    
    # Log-out
    puts <<HTML
<form method="POST" action="#{File.basename(__FILE__)}"><p>
<input type="hidden" name="action" value="logout">
#{UI_LOGIN_NAME}: #{CGI.escapeHTML(@session['login'].to_s)}
<input type="submit" value="#{UI_LOGGING_OUT}">
</p></form>
HTML
    
    # Retrieve data and display
    puts "<table id=\"maintable\">"
    puts "<tr><th>#{UI_TASK}</th><th>#{UI_LAST_DATE}</th><th>#{UI_SECOND_LAST_DATE}</th></tr>"
    @db.execute("SELECT * FROM #{@@TABLE_TASKS[:name]} ORDER BY date1 DESC").each do |t|
      
      print <<HTML
<tr>      
<td>
<form class="conductbutton" method="POST" action="#{File.basename(__FILE__)}" onsubmit="javascript:return confirm('#{UI_CONFIRMING_CONDUCTING_TASK} - '+#{CGI.escapeHTML(t[@@TABLE_TASKS[:key_ids]['name']].inspect)})"><p>
<a href="#{File.basename(__FILE__)}?editform=#{t[@@TABLE_TASKS[:key_ids]['id']]}">#{CGI.escapeHTML(t[@@TABLE_TASKS[:key_ids]['name']])}</a>
<br>
<input type="hidden" name="action" value="conduct_task">
<input type="hidden" name="task_id" value="#{t[@@TABLE_TASKS[:key_ids]['id']]}">
<input class="conduct" type="submit" value="#{UI_BUTTON_CONDUCTED}">
</p></form>
</td>
<td>#{datestr t[@@TABLE_TASKS[:key_ids]['date1']]}</td>
<td>#{datestr t[@@TABLE_TASKS[:key_ids]['date2']]}</td>
</tr>
HTML
    end
    
    puts <<HTML
</table>
<p>#{UI_TO_UPDATE_OR_DELETE_TASK}</p>
<h2>#{UI_ADDING_TASK}</h2>
<form method="POST" action="#{File.basename(__FILE__)}"><p>
<input type="hidden" name="action" value="add_task">
#{UI_TASK_NAME}: <input type="text" autocomplete="off" name="name">
<input type="submit" value="#{UI_ADDING_TASK}">
</p></form>
HTML
    footer
  end
  
  def action_no_user_get
    header
    display_errormsg
    
    print <<HTML
<p>#{UI_NO_USER}</p>
<form method="POST" action="#{File.basename(__FILE__)}"><p>
<input type="hidden" name="action" value="add_user">
#{UI_USER_NAME} <input type="text" name="name"><br>
#{UI_PASSWORD} <input type="password" name="pass"><br>
#{UI_PASSWORD_AGAIN} <input type="password" name="pass2"><br>
<input type="submit" value="#{UI_ADDING_USER}">
</p></form>
HTML
    footer
  end
  
  def action_login_get
    header
    display_errormsg
    print <<HTML
<p>#{UI_NOT_LOGGED_IN}</p>
<form method="POST" action="#{File.basename(__FILE__)}"><p>
<input type="hidden" name="action" value="login">
#{UI_USER_NAME} <input type="text" name="name"><br>
#{UI_PASSWORD} <input type="password" name="pass"><br>
<input type="submit" value="#{UI_LOGIN}">
</p></form>
HTML
    footer
  end
  
  # ============================================================
  # Entry point
  # ============================================================
  def initialize
    @cgi = CGI.new
    
    # ------------------------------------------------------------
    # Checking the login status
    # ------------------------------------------------------------
    # Checking whether there is a session,
    # together with retrieving the error messages
    
    @errormsg = []
    session_kept_keys = ['login']
    session_kept = {}
    
    @session = CGI::Session.new(@cgi)
    unless @session['errormsg'].to_s.empty?
      @errormsg = @session['errormsg'].split("\n").map{ |e| CGI.unescape(e) }
    end
    
    # Keep some values for the new session
    session_kept_keys.each{ |key| session_kept[key] = @session[key].to_s }
    
    # Create a new session
    @session = CGI::Session.new(@cgi, 'new_session' => true, 'session_expires' => Time.now + SESSION_DURATION)
    session_kept.each_pair{ |key, val| @session[key] = val }
    
    # ------------------------------------------------------------
    # Checking the database
    # ------------------------------------------------------------
    begin
      @db = SQLite3::Database.new(DB_FILE_NAME)
    rescue
      open(DB_FILE_NAME, 'a').close
    end
    
    # Check whether the user table exists
    tables_users = @db.execute("SELECT tbl_name, sql FROM sqlite_master WHERE tbl_name LIKE '#{@@TABLE_USERS[:name]}'")
    if tables_users.empty?
      STDERR.puts "Conducting \"#{@@TABLE_USERS[:sql]}\""
      @db.execute(@@TABLE_USERS[:sql])
    elsif tables_users.size > 1 || tables_users[0][1] != @@TABLE_USERS[:sql]
      raise "Invalid database file ..."
      exit
    end
    
    # Check whether the task table exists
    tables_tasks = @db.execute("SELECT tbl_name, sql FROM sqlite_master WHERE tbl_name LIKE '#{@@TABLE_TASKS[:name]}'")
    if tables_tasks.empty?
      STDERR.puts "Conducting \"#{@@TABLE_TASKS[:sql]}\""
      @db.execute(@@TABLE_TASKS[:sql])
    elsif tables_tasks.size > 1 || tables_tasks[0][1] != @@TABLE_TASKS[:sql]
      raise "Invalid database file ..."
      exit
    end
    
    @users = @db.execute("SELECT * FROM #{@@TABLE_USERS[:name]}")
    if @users.empty?
      @session['login'] = ''
      if @cgi.request_method.to_s.upcase == 'POST'
        action_no_user_post
      else
        action_no_user_get
      end
    elsif @session['login'].to_s.empty?
      if @cgi.request_method.to_s.upcase == 'POST'
        action_login_post
      else
        action_login_get
      end
    else
      if @cgi.request_method.to_s.upcase == 'POST'
        action_main_post
      else
        action_main_get
      end
    end
  end
end

LastUpdate.new

