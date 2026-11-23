import os

from app import create_app, socketio

app = create_app(start_sched=True)

if __name__ == "__main__":
    # Use eventlet worker on Render (production); fall back to Flask dev server locally.
    if os.environ.get("RENDER"):
        import socketio
        server = socketio.WSGIApp(app, socketio)
        from wsgiref.simple_server import make_server
        port = int(os.environ.get("PORT", 5000))
        with make_server("0.0.0.0", port, server) as httpd:
            print(f"Listening on 0.0.0.0:{port}")
            httpd.serve_forever()
    else:
        socketio.run(
            app,
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )