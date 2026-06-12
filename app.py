from multiprocessing.util import debug

from flask import Flask, render_template, redirect, url_for, request, session, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from models import db, User, Category, Post, Critique, AuditLog, Vote, UpcomingChange, Report, Suggestion, UserContact, Project
from sqlalchemy import or_, func, desc
from sqlalchemy.orm import selectinload
from functools import wraps
from datetime import datetime, timedelta
import time
import os
from werkzeug.utils import secure_filename
from math import ceil
import html

app = Flask(__name__)
app.config["SECRET_KEY"] = "in the years to come i will look back on this moment and smile knowing that i was able to create something that can help others grow and learn from each other"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.permanent_session_lifetime = timedelta(days=7)

db.init_app(app)
migrate = Migrate(app, db)

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("You must be logged in to access this page.", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view

def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id") or not session.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)
    return wrapped_view

def log_action(action, target_type=None, target_id=None, details=None):
    try:
        actor_id = session.get("user_id") if "user_id" in session else None
        
        log = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

def create_default_admin():
    admin_email = "josalimaxwell@gmail.com"

    existing_user = User.query.filter_by(email=admin_email).first()
    if existing_user:
        return

    admin = User(
        username="superadmin",
        email=admin_email,
        password_hash=generate_password_hash("maxterpen"),
        is_admin=True
    )

    db.session.add(admin)
    db.session.commit()

LAST_SEEN_THROTTLE = timedelta(seconds=30)
ONLINE_WINDOW = timedelta(minutes=5)

@app.before_request
def update_last_seen():
    user_id = session.get("user_id")
    if not user_id:
        return

    user = User.query.get(user_id)
    if not user:
        return

    now = datetime.utcnow()

    if not user.last_seen or user.last_seen < now - LAST_SEEN_THROTTLE:
        user.last_seen = now
        db.session.commit()

def last_seen_text(last_seen):
    if not last_seen:
        return "never"

    delta = datetime.utcnow() - last_seen
    minutes = int(delta.total_seconds() / 60)

    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} minutes ago"
    if minutes < 1440:
        return f"{minutes // 60} hours ago"
    return f"{minutes // 1440} days ago"

MIN_CRITIQUES_THRESHOLD = 3

def can_user_submit_post(user_id: int) -> bool:
    if not user_id:
        return False

    try:

        available_peer_posts = (
            db.session.query(func.count(Post.id))
            .filter(
                (Post.is_locked == False) | (Post.is_locked == None),
                Post.user_id != user_id  # Must be from other developers
            )
            .scalar() or 0
        )
        
        if available_peer_posts < 3:
            return True

        user_critique_count = (
            db.session.query(func.count(func.distinct(Critique.post_id)))
            .join(Post, Post.id == Critique.post_id)
            .filter(
                Critique.user_id == user_id,
                Post.user_id != user_id  # Exclude any self-critiques
            )
            .scalar() or 0
        )
        
        return user_critique_count >= 3

    except Exception as e:

        print(f"Error checking submission permissions: {e}")
        return True

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session.permanent = True
        login_input = request.form.get("login")
        password = request.form.get("password")

        if "@" in login_input:
            user = User.query.filter_by(email=login_input).first()
        else:
            user = User.query.filter_by(username=login_input).first()

        if user and check_password_hash(user.password_hash, password):
            if user.is_banned:
                log_action("login_blocked_banned", "user", user.id)
                flash("This account has been suspended.", "error")
                return redirect(url_for("login"))

            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["is_admin"] = user.is_admin

            log_action("login_success", "user", user.id)
            return redirect(url_for("feed"))

        log_action("login_failed", details={"login_input": login_input})
        flash("Invalid username/email or password.", "error")

    return render_template("login.html")

@app.context_processor
def inject_user():
    return {
        "is_logged_in": "user_id" in session,
        "is_admin": session.get("is_admin", False)
    }

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            is_admin=False
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            log_action("user_signup", "user", new_user.id)
            flash("Account created successfully! You can now log in.", "success")
            return redirect(url_for("login"))
        except IntegrityError:
            db.session.rollback()
            flash("Username or email already exists. Please choose another.", "error")

    return render_template("signup.html")

@app.route("/critique_landing")
def landing() :
    return render_template("landing.html")

@app.route("/", methods=["GET", "POST"])
@app.route("/feed", methods=["GET", "POST"])
def feed():
    can_submit = False 
    if 'user_id' in session:
        can_submit = can_user_submit_post(session["user_id"])

    if request.method == "POST":
        if not session.get("user_id"):
            flash("You must be logged in to post.", "error")
            return redirect(url_for("login"))

        user_id = session["user_id"]
        title = request.form.get("title")
        context = request.form.get("context")
        link = request.form.get("link")
        category_id = request.form.get("category_id", type=int)
        project_id = request.form.get("project_id", type=int) or None  # Handle empty choice safely

        project_history = (
            Post.query
            .filter_by(project_id=project_id)
            .order_by(Post.version_number.desc())
            .all()
        )

        # 3. Calculate the next version logic safely based on existing posts in this track
        highest_version = project_history[0].version_number if project_history else 0
        suggested_version = highest_version + 1

        if not title or not category_id:
            return redirect(url_for("feed"))

        # Image Upload Processing Pipeline
        image_path = None
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename != "":
                # BUGFIX: Enforce allowed extensions on the feed route to block dangerous files
                if not allowed_file(file.filename):
                    return redirect(url_for("feed"))

                filename = secure_filename(file.filename)
                
                # Setup folder inside static if it doesn't exist yet
                upload_dir = os.path.join(app.root_path, 'static', 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                
                # Unique timestamp prefix to completely prevent file collision overwrites
                unique_filename = f"{int(time.time())}_{filename}"
                file.save(os.path.join(upload_dir, unique_filename))
                
                # Store relative static path for render engines matching your template asset query
                image_path = f"uploads/{unique_filename}"

        # Build and append item instance to DB session
        new_post = Post(
            title=title,
            context=context,
            link=link,
            category_id=category_id,
            project_id=project_id,
            user_id=user_id,
            image_path=image_path,
            version_number=suggested_version
        )
        
        try:
            db.session.add(new_post)
            db.session.commit()
        except Exception as e:
            db.session.rollback()

        return redirect(url_for("feed"))

    # SECURITY FIX (Reflected XSS): Coerce ID parameters into strict ints immediately.
    # If a non-integer or script payload is passed into category, category_id cleanly defaults to None.
    category_id = request.args.get("category", type=int)
    page = request.args.get("page", 1, type=int)
    per_page = 25

    # SECURITY FIX (Reflected XSS): Extract string params and apply backend HTML escaping
    # before they are ever returned or checked by your rendering pipeline.
    raw_sort = request.args.get("sort_feed", "")
    raw_category_string = request.args.get("category", "")
    
    current_sort = html.escape(raw_sort)
    current_category = html.escape(raw_category_string)

    query = (
        db.session.query(
            Post,
            func.coalesce(func.sum(Vote.vote), 0).label("score")
        )
        .outerjoin(Vote, Vote.post_id == Post.id)
        .group_by(Post.id)
    )

    if category_id:
        query = query.filter(Post.category_id == category_id)

    # Filtering parameters logic stack
    if current_sort == "best":
        query = query.order_by(desc("score"))
    elif current_sort == "rising":
        query = query.order_by(desc(Post.created_at))
    elif current_sort == "hot":
        query = query.order_by(
            (
                func.coalesce(func.sum(Vote.vote), 0) /
                func.greatest(
                    func.extract("epoch", func.now() - Post.created_at),
                    1
                )
            ).desc()
        )
    # BUGFIX: Fall back to score sorting if "star" filter is clicked to prevent 
    # crashing on a missing model column (Post.star_count doesn't exist).
    elif current_sort == "star":
        query = query.order_by(desc("score"))
    else:
        query = query.order_by(Post.created_at.desc())

    total_items = query.count()
    total_pages = ceil(total_items / per_page)

    posts = (
        query
        .filter(Post.is_locked == False)
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )

    for post, _ in posts:
        if post.created_at:
            post.formatted_date = post.created_at.strftime('%I %p, %b %d').lstrip('0')
        else:
            post.formatted_date = "Just Now"

    upcoming_changes = UpcomingChange.query.order_by(
        UpcomingChange.created_at.desc()
    ).limit(2).all()

    user = None
    is_logged_in = False
    if session.get("user_id"):
        user = User.query.get(session["user_id"])
        if user:
            is_logged_in = True

    return render_template(
        "index.html",
        posts=posts,
        page=page,
        total_pages=total_pages,
        categories=Category.query.order_by(Category.name.asc()).all(),
        upcoming_changes=upcoming_changes,
        user=user,
        is_logged_in=is_logged_in,
        current_sort=current_sort,         # Passed down completely sanitized
        current_category=current_category, # Passed down completely sanitized
        can_submit=can_submit
    )

@app.route("/upcoming")
def upcoming_changes():
    status = request.args.get("status")
    category = request.args.get("category")

    query = UpcomingChange.query.filter_by(is_public=True)

    query = query.filter(UpcomingChange.status != "cancelled")

    if status:
        query = query.filter_by(status=status)

    if category:
        query = query.filter_by(category=category)

    changes = query.order_by(
        UpcomingChange.priority.asc(),
        UpcomingChange.created_at.desc()
    ).all()

    return render_template(
        "upcoming.html",
        changes=changes,
        active_status=status,
        active_category=category
    )

@app.route("/post/<int:post_id>")
def view_post(post_id):
    post = Post.query.get_or_404(post_id)

    if post.is_locked and (not session.get("is_admin")):
        log_action("post_blocked", "user", post.id)
        return redirect(url_for("feed"))

    project_timeline = []
    if post.project_id:
        project_timeline = (
            Post.query.filter_by(project_id=post.project_id)
            .order_by(Post.version_number.desc())
            .all()
        )

    critiques = (
        Critique.query
        .options(selectinload(Critique.replies))
        .filter_by(post_id=post_id, parent_id=None)
        .order_by(Critique.created_at.asc())
        .all()
    )
 
    post_score = (
        db.session.query(func.coalesce(func.sum(Vote.vote), 0))
        .filter(Vote.post_id == post_id)
        .scalar()
    )

    vote_count = (
        db.session.query(func.count(Vote.id))
        .filter(Vote.post_id == post_id)
        .scalar()
    )

    user = None
    user_vote = None

    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        user_vote = Vote.query.filter_by(
            post_id=post_id,
            user_id=user_id
        ).first()

    return render_template("post.html",
                            user=user,
                            post=post,
                            project_timeline=project_timeline,
                            critiques=critiques,
                            post_score=post_score, 
                            vote_count=vote_count,
                            user_vote=user_vote)

@app.route("/vote/<int:post_id>", methods=["POST"])
def vote(post_id):
    user_id = session.get("user_id")
    if not user_id:
        abort(403)

    data = request.get_json(silent=True)

    try:
        value = int(
            data["value"] if data is not None else request.form["value"]
        )
    except (KeyError, TypeError, ValueError):
        abort(400)

    if value not in (-1, 1):
        abort(400)

    existing_vote = Vote.query.filter_by(
        post_id=post_id,
        user_id=user_id
    ).first()

    if existing_vote:
        if existing_vote.vote == value:
            db.session.delete(existing_vote)   # toggle off
            user_vote = 0
        else:
            existing_vote.vote = value         # switch
            user_vote = value
    else:
        db.session.add(
            Vote(post_id=post_id, user_id=user_id, vote=value)
        )
        user_vote = value

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409)

    post_score = (
        db.session.query(db.func.coalesce(db.func.sum(Vote.vote), 0))
        .filter(Vote.post_id == post_id)
        .scalar()
    )

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({
            "score": post_score,
            "user_vote": user_vote
        })

    return redirect(url_for("view_post", post_id=post_id))

@app.route("/critique/<int:post_id>", methods=["POST"])
def submit_critique(post_id):
    if "user_id" not in session:
        flash("You must be logged in to submit a critique.", "error")
        return redirect(url_for("login"))

    content = request.form.get("critique")
    parent_id = request.form.get("parent_id")

    if not content:
        return redirect(url_for("view_post", post_id=post_id))

    try:
        new_critique = Critique(
            content=content,
            user_id=session["user_id"],
            post_id=post_id,
            parent_id=parent_id if parent_id else None
        )

        db.session.add(new_critique)
        db.session.commit()

        log_action(
            "critique_created",
            target_type="critique",
            target_id=new_critique.id,
            details={
                "post_id": post_id,
                "parent_id": parent_id
            }
        )

    except Exception:
        db.session.rollback()

    return redirect(url_for("view_post", post_id=post_id))

@app.route("/report/<string:target_type>/<int:target_id>/<int:return_post>/", methods=["GET", "POST"])
@login_required
def report_content(target_type, target_id, return_post):
    user = User.query.get(session["user_id"])

    allowed_targets = {"post", "comment", "user"}
    if target_type not in allowed_targets:
        abort(404)

    if target_type == "post":
        target = Post.query.get_or_404(target_id)
        redirect_url = url_for("view_post", post_id=target_id)

    elif target_type == "comment":
        target = Critique.query.get_or_404(target_id)
        redirect_url = url_for("view_post", post_id=target.post_id)

    else:  
        target = User.query.get_or_404(target_id)
        redirect_url = url_for("profile", user_id=target.id)

    if request.method == "POST":
        reason = request.form.get("reason")
        description = request.form.get("description")

        if not reason:
            return redirect(request.url)

        exists = Report.query.filter_by(
            reporter_id=session["user_id"],
            target_type=target_type,
            target_id=target_id
        ).first()

        if exists:
            return redirect(redirect_url)

        report = Report(
            reporter_id=session["user_id"],
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            description=description
        )

        db.session.add(report)
        db.session.commit()

        return redirect(redirect_url)

    return render_template(
        "report_content.html",
        user=user,
        return_post=return_post,
        target_id=target_id,
        target_type=target_type,
        target=target
    )


@app.route("/submit", methods=["GET", "POST"])
@login_required
def submit_project():
    user_projects = (
        Project.query
        .filter_by(owner_id=session["user_id"])
        .order_by(Project.created_at.desc())
        .all()
    )
    categories = Category.query.order_by(Category.name.asc()).all()

    # Determine if the user is allowed to submit (passed to the template for elegant UI styling)
    can_submit = can_user_submit_post(session["user_id"])

    if request.method == "POST":
        # Hard enforcement check right at the point of submission execution
        if not can_submit:
            flash(
                "You must critique at least 3 different projects before submitting your own.",
                "error"
            )
            return redirect(url_for("submit_project"))

        title = request.form.get("title")
        link = request.form.get("link")
        context = request.form.get("context")
        feedback = request.form.get("feedback")
        image = request.files.get("image")
        category_id = request.form.get("category")
        project_id = request.form.get("project_id")
        
        is_new_project = request.form.get('is_new_project') == 'true'

        if not title:
            flash("Title is required.", "error")
            return redirect(url_for("submit_project"))

        image_path = None
        if image and image.filename:
            if not allowed_file(image.filename):
                flash("Invalid image type.", "error")
                return redirect(request.url)

            filename = secure_filename(image.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image.save(save_path)
            image_path = f"uploads/{filename}"

        try:
            assigned_project_id = None
            version_number = 1

            if is_new_project:
                new_project = Project(
                    name=title,
                    owner_id=session["user_id"]
                )
                db.session.add(new_project)
                db.session.flush()  
                assigned_project_id = new_project.id
                version_number = 1

            elif project_id and project_id.strip() != "":
                project = Project.query.get_or_404(int(project_id))

                if project.owner_id != session["user_id"]:
                    flash("You do not own this project.", "error")
                    return redirect(url_for("submit_project"))

                assigned_project_id = project.id
                
                highest_version = (
                    db.session.query(db.func.max(Post.version_number))
                    .filter(Post.project_id == assigned_project_id)
                    .scalar()
                )
                version_number = (highest_version or 0) + 1
            
            post = Post(
                title=title,
                link=link,
                context=context,
                feedback=feedback,
                image_path=image_path,
                user_id=session["user_id"],
                category_id=int(category_id) if category_id else None,
                project_id=assigned_project_id,
                version_number=version_number
            )

            db.session.add(post)
            db.session.commit()

            log_action(
                "post_created",
                target_type="post",
                target_id=post.id,
                details={
                    "project_id": assigned_project_id,
                    "version": version_number
                }
            )

            return redirect(url_for("feed"))

        except Exception as e:
            db.session.rollback()
            flash("Something went wrong. Please try again.", "error")
            return redirect(url_for("submit_project"))

    # Passing `can_submit` flags safely out to the Jinja layout environment
    return render_template(
        "submit.html",
        categories=categories,
        user_projects=user_projects,
        can_submit=can_submit
    )

@app.route("/profile/<int:user_id>")
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    current_user = User.query.get(session["user_id"])

    # 1. Fetch multi-version Projects (where project_id is NOT NULL)
    user_projects = (
        db.session.query(Project)
        .filter(Project.owner_id == user.id)
        .join(Post, Post.project_id == Project.id)
        .group_by(Project.id)
        .order_by(db.func.max(Post.created_at).desc())
        .all()
    )

    project_snapshots = []
    for project in user_projects:
        latest_post = (
            Post.query.filter_by(project_id=project.id)
            .order_by(Post.version_number.desc())
            .first()
        )
        version_count = Post.query.filter_by(project_id=project.id).count()
        
        if latest_post:
            project_snapshots.append({
                "project": project,
                "latest_post": latest_post,
                "version_count": version_count
            })

    # 2. Fetch Standalone Posts (where project_id IS NULL)
    standalone_posts = (
        Post.query.filter_by(user_id=user.id, project_id=None)
        .order_by(Post.created_at.desc())
        .all()
    )

    # 3. Fetch critiques exactly as before
    critiques = Critique.query.filter_by(user_id=user.id).order_by(Critique.created_at.desc()).all()

    return render_template(
        "profile.html",
        user=user,
        current_user=current_user,
        project_snapshots=project_snapshots,
        standalone_posts=standalone_posts,
        critiques=critiques,
        last_seen_text=last_seen_text
    )

@app.route("/profile/avatar", methods=["POST"])
def update_avatar():
    # Enforce authentication verification
    if not session.get("user_id"):
        return redirect(url_for("feed"))
        
    user = User.query.get(session["user_id"])
    if not user:
        return redirect(url_for("feed"))

    if "profile_pic" in request.files:
        file = request.files["profile_pic"]
        if file and file.filename != "":
            # Secure file filtering parsing mechanics
            filename = secure_filename(file.filename)
            
            # Setup dynamic directories maps internally
            upload_dir = os.path.join(app.root_path, 'static', 'avatars')
            os.makedirs(upload_dir, exist_ok=True)
            
            # Timestamp suffixing to completely avoid target browser asset caching bugs
            unique_filename = f"user_{user.id}_{int(time.time())}_{filename}"
            file.save(os.path.join(upload_dir, unique_filename))
            
            # Delete old profile pic file if it exists to clean up server space
            if user.profile_pic:
                old_path = os.path.join(app.root_path, 'static', user.profile_pic)
                if os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass # Fail silently if file is locked or missing

            # Write relative storage parameters back to user row profile tracker column
            user.profile_pic = f"avatars/{unique_filename}"
            
            try:
                db.session.commit()
                flash("Profile avatar updated successfully!", "success")
            except Exception as e:
                db.session.rollback()
                flash("Database persistence error saving image.", "error")
                
    return redirect(url_for('profile', user_id=user.id))

@app.route("/profile/contact/edit", methods=["GET", "POST"])
def edit_contact():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = User.query.get_or_404(user_id)

    # ensure contact row exists
    if not user.contact:
        user.contact = UserContact(user_id=user.id)

    if request.method == "POST":
        user.contact.phone = request.form.get("phone")
        user.contact.website = request.form.get("website")
        user.contact.github = request.form.get("github")
        user.contact.twitter = request.form.get("twitter")
        user.contact.telegram = request.form.get("telegram")

        # visibility toggles (checkboxes)
        user.contact.show_phone = True if request.form.get("show_phone") else False

        user.contact.updated_at = datetime.utcnow()

        db.session.add(user.contact)
        db.session.commit()

        flash("Contact information updated successfully", "success")
        return redirect(url_for("profile", user_id=user.id))

    return render_template("edit_contact.html", user=user)

@app.route("/follow/<int:user_id>", methods=["POST"])
def follow_user(user_id):
    current_id = session.get("user_id")
    if not current_id:
        return redirect(url_for("login"))

    if current_id == user_id:
        return "You cannot follow yourself", 400

    user = User.query.get_or_404(current_id)
    target = User.query.get_or_404(user_id)

    if not user.followed.filter_by(id=target.id).first():
        user.followed.append(target)
        db.session.commit()

    return redirect(url_for("profile", user_id=user_id))

@app.route("/unfollow/<int:user_id>", methods=["POST"])
def unfollow_user(user_id):
    current_id = session.get("user_id")
    if not current_id:
        return redirect(url_for("login"))

    user = User.query.get_or_404(current_id)
    target = User.query.get_or_404(user_id)

    if user.followed.filter_by(id=target.id).first():
        user.followed.remove(target)
        db.session.commit()

    return redirect(url_for("profile", user_id=user_id))


from datetime import datetime

@app.route('/projects/update/<int:post_id>', methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    # 1. Fetch the baseline post the user wants to update from
    origin_post = Post.query.get_or_404(post_id)
    project_name = Project.query.get(origin_post.project_id).name if origin_post.project_id else "Standalone Post"

    # Security Check: Ensure session user matches post author
    if session.get('user_id') != origin_post.user_id:
        flash("You do not have permission to update this post.", "error")
        return redirect(url_for('feed'))

    # If this post wasn't saved as/linked to a project repository tracking container
    if not origin_post.project_id:
        flash("Standalone posts cannot be updated with version increments. Link it to a project container first.", "error")
        return redirect(url_for('feed'))

    # 2. Fetch all historical posts/updates that share this same project track container
    project_history = (
        Post.query
        .filter_by(project_id=origin_post.project_id)
        .order_by(Post.version_number.desc())
        .all()
    )

    # 3. Calculate the next version logic safely based on existing posts in this track
    highest_version = project_history[0].version_number if project_history else 0
    suggested_version = highest_version + 1

    if request.method == 'POST':
        title = request.form.get('title') or f"Update to {origin_post.title}"
        context = request.form.get('context') # What changed / what is the current focus
        feedback = request.form.get('feedback') # Specific critique points for this phase
        link = request.form.get('link')
        image = request.files.get('image')

        # Fallback to the original post's image if no new one is provided
        image_path = origin_post.image_path

        if image and image.filename:
            if not allowed_file(image.filename):
                flash("Invalid image type.", "error")
                return redirect(request.url)
                
            filename = secure_filename(image.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image.save(save_path)
            image_path = f"uploads/{filename}"

        try:
            # 4. Save this update iteration as a new standalone entry pointing to the main project track
            new_version_post = Post(
                title=title,
                link=link,
                context=context,
                feedback=feedback,
                image_path=image_path,
                user_id=session["user_id"],
                category_id=origin_post.category_id, # Inherit the category assignment from the origin track
                project_id=origin_post.project_id,   # Tie securely to the same repository tracking track
                version_number=suggested_version     # Push the newly incremented target iteration mark
            )

            db.session.add(new_version_post)
            db.session.commit()

            log_action(
                "post_created",
                target_type="post",
                target_id=new_version_post.id,
                details={
                    "project_id": origin_post.project_id,
                    "version": suggested_version,
                    "is_update": True
                }
            )

            flash(f"Project updated successfully to Version {suggested_version}!", "success")
            return redirect(url_for('feed'))

        except Exception as e:
            db.session.rollback()
            flash("Error processing project version update: " + str(e), "error")
            return redirect(url_for('update_post', post_id=origin_post.id))

    return render_template(
        'update_project.html',
        origin_post=origin_post,
        project_history=project_history,  # Sent to frontend to render a neat timeline or changelog stack
        suggested_version=suggested_version,
        project_name=project_name
    )

@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)

    if "user_id" not in session or session["user_id"] != post.user_id:
        flash("You do not have permission to edit this post.", "error")
        return redirect(url_for("feed"))

    if request.method == "POST":
        title = request.form.get("title")
        context = request.form.get("context")
        feedback = request.form.get("feedback")
        image = request.files.get('image')

        if not title:
            flash("Title is required.", "error")
            return redirect(url_for("edit_post", post_id=post_id))
        
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            unique_filename = f"edit_{int(time.time())}_{filename}"
            
            upload_dir = os.path.join(app.root_path, 'static', 'uploads')
            image.save(os.path.join(upload_dir, unique_filename))
            
            image_path = f"uploads/{unique_filename}"

        try:
            post.title = title
            post.context = context
            post.feedback = feedback
            if image and image.filename != '':
                filename = secure_filename(image.filename)
                unique_filename = f"edit_{int(time.time())}_{filename}"
                
                # Clean up the old layout file if it exists
                if post.image_path:
                    old_path = os.path.join(app.root_path, 'static', post.image_path)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass

                image_path = f"uploads/{unique_filename}"
            post.image_path = image_path if image and image.filename != '' else post.image_path
            db.session.commit()
            log_action("post_edited",target_type="post",target_id=post.id,details={"title": title})
            flash("Post updated successfully.", "success")
            return redirect(url_for("view_post", post_id=post_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating post: {str(e)}", "error")

    return render_template("edit_post.html", post=post, categories=Category.query.all())

@app.route("/delete/<int:user_id>/<int:post_id>", methods=["POST"])
@login_required
def user_delete_post(user_id, post_id):
    post = Post.query.get_or_404(post_id)
    user = User.query.get_or_404(user_id)
    db.session.delete(post)
    db.session.commit()
    log_action("post_deleted",target_type="post",target_id=post.id,details={"title": post.title})
    flash("Post deleted successfully.", "success")
    return redirect(url_for("profile", user_id=user.id))

@app.route("/delete-critique/<int:critique_id>", methods=["POST"])
@login_required
def delete_critique(critique_id):
    critique = Critique.query.get_or_404(critique_id)

    if session["user_id"] != critique.user_id and not session.get("is_admin"):
        return redirect(url_for("view_post", post_id=critique.post_id))

    db.session.delete(critique)
    db.session.commit()
    log_action("critique_deleted",target_type="critique",target_id=critique.id,details={"post_id": critique.post_id})
    return redirect(url_for("view_post", post_id=critique.post_id))

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username, is_admin=True).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["is_admin"] = True
            log_action("admin_login_success", "user", user.id)
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin credentials.", "error")
    return render_template("admin_login.html")

@app.route("/ars-0tq-b79", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    user_count = User.query.count()
    post_count = Post.query.count()
    category_count = Category.query.count()

    username = session.get("username")
    first_letter = username[0].upper() if username else "U"

    latest_logs = (
        AuditLog.query
        .order_by(AuditLog.created_at.desc())
        .limit(7)
        .all()
    )

    post_reports = (
        Report.query
        .filter(Report.target_type == "post")
        .count()
    )

    user_reports = (
        Report.query
        .filter(Report.target_type == "user")
        .count()
    )

    online_threshold = datetime.utcnow() - ONLINE_WINDOW

    online_count = User.query.filter(
        User.last_seen >= online_threshold
    ).count()

    queue_pending_post_reports = (
        Report.query
        .filter(
            Report.target_type == "post",
            Report.status == "open"
        )
        .order_by(Report.created_at.asc())
        .limit(3)
        .all()
    )

    # Get the IDs of heavily reported posts
    flagged_post_ids = (
        db.session.query(Report.target_id)
        .filter(Report.target_type == "post", Report.status == "open")
        .group_by(Report.target_id)
        .having(func.count(Report.id) >= 2)
        .all()
    )
    flagged_ids = [r[0] for r in flagged_post_ids]

    # Fetch the actual post records cleanly
    queue_flagged_post_reports = Post.query.filter(Post.id.in_(flagged_ids)).limit(3).all()

    queue_user_reports = (
        Report.query
        .join(User, User.id == Report.target_id)
        .filter(
            Report.target_type == "user",
            Report.status == "open",
            User.is_banned.is_(False)
        )
        .order_by(Report.created_at.asc())
        .limit(3)
        .all()
    )

    user_reports = (
        db.session.query(Report.target_id)
        .filter(
            Report.target_type == "user",
            Report.status == "open"
        )
        .distinct()
        .count()
    )

    post_reports = (
        db.session.query(Report.target_id)
        .filter(
            Report.target_type == "post",
            Report.status == "open"
        )
        .distinct()
        .count()
    )

    return render_template(
        "admin_dashboard.html",
        user_count=user_count,
        post_count=post_count,
        category_count=category_count,
        first_letter=first_letter,
        latest_logs=latest_logs,
        post_reports=post_reports,
        user_reports=user_reports,
        online_threshold=online_threshold,
        online_count=online_count,
        user_reports_count=user_reports,
        post_reports_count=post_reports,

        # FIXED QUEUE OUTPUT
        queue_pending_post_reports=queue_pending_post_reports,
        queue_flagged_post_reports=queue_flagged_post_reports,
        queue_user_reports=queue_user_reports
    )

@app.route("/admin/users")
@admin_required
def admin_users():

    users = User.query.order_by(User.created_at.desc()).all()

    user_data = []

    for user in users:

        reports_filed = (
            db.session.query(Report)
            .filter(Report.reporter_id == user.id)
            .count()
        )

        reports_received = (
            db.session.query(Report)
            .filter(
                Report.target_type == "user",
                Report.target_id == user.id
            )
            .count()
        )

        user_data.append({
            "user": user,
            "reports_filed": reports_filed,
            "reports_received": reports_received
        })

    return render_template("admin_users.html", user_data=user_data)

@app.route("/admin/users/toggle-admin/<int:user_id>", methods=["POST"])
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == session.get("user_id"):
        flash("You cannot change your own admin status.", "error")
        return redirect(url_for("admin_users"))

    user.is_admin = not user.is_admin
    db.session.commit()
    log_action("admin_role_toggled",target_type="user",target_id=user.id,details={"new_is_admin": user.is_admin})

    return redirect(url_for("admin_users"))

@app.route("/admin/users/toggle-ban/<int:user_id>", methods=["POST"])
@admin_required
def toggle_ban(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == session.get("user_id"):
        flash("You cannot ban yourself.", "error")
        return redirect(url_for("admin_users"))

    user.is_banned = not user.is_banned
    db.session.commit()
    log_action("user_ban_toggled",target_type="user",target_id=user.id,details={"new_is_banned": user.is_banned})

    return redirect(url_for("admin_users"))

@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == session.get("user_id"):
        flash("You cannot delete yourself.", "error")
        return redirect(url_for("admin_users"))

    log_action("user_deleted",target_type="user",target_id=user.id,details={"email": user.email, "username": user.username})
    db.session.delete(user)
    db.session.commit()

    return redirect(url_for("admin_users"))

@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    if request.method == "POST":
        print("FORM DATA:", request.form)
        category_id = request.form.get("category_id")
        name = request.form.get("category_name", "").strip()

        if not name:
            flash("Category name cannot be empty.", "error")
            return redirect(url_for("admin_categories"))

        try:
            if category_id:
                # UPDATE
                category = Category.query.get_or_404(category_id)
                category.name = name
                category.description = request.form.get("category_description", "").strip()
                category.rules = request.form.get("category_rules", "").strip()

                log_action(
                    "category_updated",
                    target_type="category",
                    target_id=category.id,
                    details={"name": category.name},
                )

                flash("Category updated successfully.", "success")

            else:
                # CREATE
                category = Category(
                    name=name,
                    description=request.form.get("category_description", "").strip(),
                    rules=request.form.get("category_rules", "").strip()
                )

                db.session.add(category)

                log_action(
                    "category_created",
                    target_type="category",
                    target_id=None,
                    details={"name": name},
                )

                flash("Category created successfully.", "success")

            db.session.commit()

        except IntegrityError:
            db.session.rollback()
            flash("Database error. Try again.", "error")

        return redirect(url_for("admin_categories"))

    categories = Category.query.order_by(Category.created_at.desc()).all()
    return render_template("admin_categories.html", categories=categories)

@app.route("/admin/categories/delete/<int:category_id>", methods=["POST"])
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)

    has_posts = (
        db.session.query(Post.id)
        .filter(Post.category_id == category_id)
        .first()
        is not None
    )

    if has_posts:
        flash(
            f"Category '{category.name}' cannot be deleted because it has posts.",
            "error"
        )
        return redirect(url_for("admin_categories"))

    log_action(
        "category_deleted",
        target_type="category",
        target_id=category.id,
        details={"name": category.name}
    )

    db.session.delete(category)
    db.session.commit()

    flash(f"Category '{category.name}' deleted successfully.", "success")
    return redirect(url_for("admin_categories"))

@app.route("/admin/posts")
@admin_required
def admin_posts():

    posts = Post.query.order_by(Post.created_at.desc()).all()

    categories = Category.query.all()

    report_counts = dict(
        db.session.query(
            Report.target_id,
            func.count(Report.id)
        )
        .filter(Report.target_type == "post")
        .group_by(Report.target_id)
        .all()
    )

    for post in posts:
        post.reports = report_counts.get(post.id, 0)

    return render_template(
        "admin_posts.html",
        posts=posts,
        categories=categories
    )

@app.route("/admin/posts/toggle-lock/<int:post_id>", methods=["POST"])
@admin_required
def toggle_lock_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.is_locked = not post.is_locked
    db.session.commit()
    log_action("post_lock_toggled",target_type="post",target_id=post.id,details={"new_is_locked": post.is_locked})
    flash(f"Post {'locked' if post.is_locked else 'unlocked'} successfully.", "success")
    return redirect(url_for("admin_posts"))

@app.route("/admin/posts/delete/<int:post_id>", methods=["POST"])
@admin_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    log_action("post_deleted",target_type="post",target_id=post.id,details={"title": post.title})
    flash("Post deleted successfully.", "success")
    return redirect(url_for("admin_posts"))

@app.route("/auditlogs")
@admin_required
def audit_logs():

    actor_id = request.args.get("actor_id", type=int)
    action = request.args.get("action", type=str)
    target_type = request.args.get("target_type", type=str)
    start_date = request.args.get("start_date", type=str)

    order = request.args.get("sort", "desc")

    query = AuditLog.query

    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    if start_date:
        try:
            date_obj = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(AuditLog.created_at >= date_obj)
        except ValueError:
            pass 

    if order == "asc":
        query = query.order_by(AuditLog.created_at.asc())
    else:
        query = query.order_by(AuditLog.created_at.desc())

    logs = query.all()
    total_logs = query.count()
    return render_template("auditlogs.html", logs=logs, total_logs=total_logs)

@app.route("/admin/reports")
@admin_required
def admin_reports():

    reports = (
        Report.query
        .order_by(
            Report.status.asc(),        # open first
            Report.created_at.desc()    # newest first
        )
        .all()
    )

    enriched_reports = []

    for report in reports:

        # safer target resolution
        target = report.get_target()

        # safe reporter fallback
        reporter = report.reporter

        enriched_reports.append({
            "report": report,
            "target": target,
            "reporter": reporter
        })

    return render_template(
        "admin_reports.html",
        enriched_reports=enriched_reports
    )

@app.route("/admin/reports/<int:report_id>", methods=["GET", "POST"])
@admin_required
def resolve_report(report_id):
    report = Report.query.get_or_404(report_id)

    if request.method == "POST":
        action = request.form.get("action")
        admin_note = request.form.get("admin_note")

        # Always update note
        report.admin_note = admin_note

        # Only resolve once (prevent overwriting history)
        is_final_state = report.status in ["resolved", "rejected"]

        if not is_final_state:
            report.resolved_by = session.get("user_id")
            report.resolved_at = datetime.utcnow()

            if action == "resolve":
                report.status = "resolved"

            elif action == "reject":
                report.status = "rejected"

            elif action == "ban_user":
                report.status = "resolved"
                # optional: actual ban logic should go here

            elif action == "delete_content":
                report.status = "resolved"
                # optional: deletion logic should go here

        db.session.commit()
        flash("Report updated successfully.", "success")
        return redirect(url_for("resolve_report", report_id=report.id))

    return render_template(
        "report_resolution.html",
        report=report,
        target=report.get_target()
    )

@app.route("/admin_delete_critique/<int:critique_id>", methods=["POST"])
@admin_required
def admin_delete_critique(critique_id):
    critique = Critique.query.get_or_404(critique_id)

    if session["user_id"] != critique.user_id and not session.get("is_admin"):
        flash("You do not have permission to delete this critique.", "error")
        return redirect(url_for("view_post", post_id=critique.post_id))

    db.session.delete(critique)
    db.session.commit()
    log_action("critique_deleted",target_type="critique",target_id=critique.id,details={"post_id": critique.post_id})
    flash("Critique deleted successfully.", "success")
    return redirect(url_for("view_post", post_id=critique.post_id))

@app.route("/rules")
def rules():
    return render_template("legal/rules.html")

@app.route("/privacy")
def privacy():
    return render_template("legal/privacy.html")

@app.route("/terms")
def terms():
    return render_template("legal/terms.html")

@app.route("/accessibility")
def accessibility():
    return render_template("legal/accessibility.html")

@app.route("/admin/upcoming", methods=["GET", "POST"])
def admin_upcoming():

    if request.method == "POST":

        change_id = request.form.get("id")

        if change_id:
            change = UpcomingChange.query.get(change_id)

            if change:
                change.title = request.form["title"]
                change.description = request.form["description"]
                change.status = request.form["status"]
                change.priority = request.form["priority"]
                change.target_version = request.form.get("target_version")


        else:
            change = UpcomingChange(
                title=request.form["title"],
                description=request.form["description"],
                status=request.form["status"],
                priority=request.form["priority"],
                target_version=request.form.get("target_version")
            )
            db.session.add(change)

        db.session.commit()

        return redirect(url_for("admin_upcoming"))

    changes = UpcomingChange.query.order_by(
        UpcomingChange.priority.asc(),
        UpcomingChange.created_at.desc()
    ).all()

    return render_template("admin_changes.html", changes=changes)

@app.route("/suggest", methods=["POST"])
def submit_suggestion():
    message = request.form.get("message")
    email = request.form.get("email")
    subscribed = bool(request.form.get("subscribe"))

    if not message:
        abort(400)

    suggestion = Suggestion(
        message=message,
        email=email,
        subscribed=subscribed,
    )

    db.session.add(suggestion)
    db.session.commit()

    return redirect(url_for("upcoming_changes"))

@app.route("/suggestions")
@admin_required
def admin_suggestions():
    suggestions = Suggestion.query.order_by(Suggestion.created_at.desc()).all()
    return render_template("admin_suggestions.html", suggestions=suggestions)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("feed"))

@app.route("/logout")
def logout():
    log_action("logout", "user", session.get("user_id"))
    session.clear()
    return redirect(url_for("feed"))

with app.app_context():
    db.create_all()         
    create_default_admin()

if __name__ == "__main__":
    app.run(debug=True)