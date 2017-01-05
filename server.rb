require 'webrick'
srv = WEBrick::HTTPServer.new({
  :DocumentRoot => './',
  :BindAddress => 'localhost',
  :Port => 8880,
  :AccessLog => [[STDERR, WEBrick::AccessLog::CLF]],
})
srv.mount_proc('/') do |req, res|
  res.set_redirect(WEBrick::HTTPStatus::Found, '/lastupdatelist.cgi')
end
srv.mount('/lastupdatelist.cgi', WEBrick::HTTPServlet::CGIHandler, 'lastupdatelist.cgi')
trap("INT"){ srv.shutdown }
srv.start
