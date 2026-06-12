from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


followers = db.Table(
    "followers",
    db.Column("follower_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("followed_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
)

class User(db.Model):
    __tablename__ = "user"

    __table_args__ = (
        db.UniqueConstraint("username", name="uq_user_username"),
        db.UniqueConstraint("email", name="uq_user_email"),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    profile_pic = db.Column(db.String(255), nullable=True)

    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports = db.Column(db.Integer, default=0)

    posts = db.relationship("Post", back_populates="user")
    projects = db.relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    vote = db.relationship("Vote", back_populates="user", cascade="all, delete-orphan")
    contact = db.relationship(
        "UserContact",
        back_populates="user",
        uselist=False
    )

    critiques_authored = db.relationship("Critique", back_populates="author", cascade="all, delete-orphan")

    followed = db.relationship(
        "User",
        secondary=followers,
        primaryjoin=(id == followers.c.follower_id),
        secondaryjoin=(id == followers.c.followed_id),
        backref=db.backref("followers", lazy="dynamic"),
        lazy="dynamic"
    )

class UserContact(db.Model):
    __tablename__ = "user_contact"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)

    phone = db.Column(db.String(30), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    github = db.Column(db.String(255), nullable=True)
    twitter = db.Column(db.String(255), nullable=True)
    telegram = db.Column(db.String(255), nullable=True)

    show_email = db.Column(db.Boolean, default=False)
    show_phone = db.Column(db.Boolean, default=False)

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship(
        "User",
        back_populates="contact"
    )

class Project(db.Model):
    __tablename__ = "project"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
     
    # Fixed: Changed backref="owned_projects" to back_populates="projects"
    owner = db.relationship("User", back_populates="projects")
    posts = db.relationship("Post", back_populates="project", cascade="all, delete-orphan")

class Category(db.Model):
    __tablename__ = "category"

    __table_args__ = (
        db.UniqueConstraint("name", name="uq_category_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255))
    rules = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posts = db.relationship("Post", backref="category", lazy=True)


class Post(db.Model):
    __tablename__ = "post"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    link = db.Column(db.String(500), nullable=True)
    context = db.Column(db.Text)
    feedback = db.Column(db.Text)
    image_path = db.Column(db.String(255), nullable=True)
    version_number = db.Column(db.Integer, default=1, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_locked = db.Column(db.Boolean, default=False)
    vote_count = db.Column(db.Integer, nullable=True, default=0)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    reports = db.Column(db.Integer, default=0)

    user = db.relationship("User", back_populates="posts")
    project = db.relationship("Project", back_populates="posts")

    critiques = db.relationship(
        "Critique",
        backref="post",
        lazy=True,
        cascade="all, delete-orphan"
    )
    vote = db.relationship("Vote", back_populates="post", cascade="all, delete-orphan")

class Critique(db.Model):
    __tablename__ = "critique"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    parent_id = db.Column(db.Integer, db.ForeignKey("critique.id"), nullable=True)

    author = db.relationship("User", back_populates="critiques_authored")

    replies = db.relationship(
        "Critique",
        backref=db.backref("parent", remote_side=[id]),
        lazy="select"
    )


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(100), nullable=False)

    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer)

    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    actor = db.relationship("User", backref="audit_logs")
    
class Vote(db.Model):
    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id'),
    )
    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    vote = db.Column(db.Integer, nullable=False, default=0)

    post = db.relationship("Post", back_populates="vote")
    user = db.relationship("User", back_populates="vote")

class UpcomingChange(db.Model):
    __tablename__ = "upcoming_changes"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="planned"
    )

    priority = db.Column(
        db.Integer,
        default=3
    )

    target_version = db.Column(db.String(20), nullable=True)
    target_date = db.Column(db.Date, nullable=True)

    category = db.Column(
        db.String(50),
        nullable=True
    )

    is_public = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)

    reporter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    target_type = db.Column(db.String(20), nullable=False)

    target_id = db.Column(db.Integer, nullable=False)

    reason = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), default="open", nullable=False)

    admin_note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resolved_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    reporter = db.relationship(
        "User",
        foreign_keys=[reporter_id],
        backref="reports_made"
    )

    def get_target(self):
        model_map = {
            "post": Post,
            "comment": Critique,
            "user": User
        }

        model = model_map.get(self.target_type)
        if not model:
            return None

        # Modern execution style 
        return db.session.get(model, self.target_id)

class Suggestion(db.Model):
    __tablename__ = "suggestions"

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(255), nullable=True)
    subscribed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<Suggestion {self.id}>"
    