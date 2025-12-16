from datetime import datetime
from flask import Flask, request, redirect, flash, render_template_string
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///events.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'secure-key'

db = SQLAlchemy(app)

# ---------------- MODELS ----------------

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    description = db.Column(db.String(200))


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)


class Allocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id'), nullable=False)

    event = db.relationship(Event)
    resource = db.relationship(Resource)


# ---------------- UTIL FUNCTIONS ----------------

def parse_datetime(value):
    """Safely parse HTML datetime-local input"""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def has_conflict(resource_id, start, end, event_id=None):
    allocations = Allocation.query.filter_by(resource_id=resource_id).all()

    for alloc in allocations:
        if event_id and alloc.event_id == event_id:
            continue

        e = alloc.event
        if start < e.end_time and e.start_time < end:
            return True
    return False


# ---------------- ROUTES ----------------

@app.route('/')
def index():
    events = Event.query.order_by(Event.start_time).all()
    return render_template_string("""
    <h2>Events</h2>
    <a href="/add-event">Add Event</a> |
    <a href="/resources">Resources</a> |
    <a href="/allocate">Allocate Resource</a> |
    <a href="/report">Utilisation Report</a>
    <hr>

    {% for e in events %}
        <p>
            <b>{{e.title}}</b><br>
            {{e.start_time}} → {{e.end_time}}<br>
            {{e.description}}
        </p>
    {% else %}
        <p>No events created yet.</p>
    {% endfor %}
    """, events=events)


@app.route('/add-event', methods=['GET', 'POST'])
def add_event():
    if request.method == 'POST':
        start = parse_datetime(request.form['start'])
        end = parse_datetime(request.form['end'])

        if start >= end:
            flash("End time must be after start time")
            return redirect('/add-event')

        db.session.add(Event(
            title=request.form['title'],
            start_time=start,
            end_time=end,
            description=request.form['desc']
        ))
        db.session.commit()
        flash("Event created")
        return redirect('/')

    return render_template_string("""
    <h3>Add Event</h3>
    {% for m in get_flashed_messages() %}
        <p>{{m}}</p>
    {% endfor %}
    <form method="post">
        Title: <input name="title" required><br><br>
        Start: <input type="datetime-local" name="start" required><br><br>
        End: <input type="datetime-local" name="end" required><br><br>
        Description: <input name="desc"><br><br>
        <button>Add</button>
    </form>
    """)


@app.route('/resources', methods=['GET', 'POST'])
def resources():
    if request.method == 'POST':
        db.session.add(Resource(
            name=request.form['name'],
            type=request.form['type']
        ))
        db.session.commit()
        flash("Resource added")

    resources = Resource.query.all()
    return render_template_string("""
    <h3>Resources</h3>
    {% for m in get_flashed_messages() %}
        <p>{{m}}</p>
    {% endfor %}

    <form method="post">
        Name: <input name="name" required>
        Type: <input name="type" required>
        <button>Add</button>
    </form>
    <hr>

    {% for r in resources %}
        <p>{{r.name}} ({{r.type}})</p>
    {% else %}
        <p>No resources added yet.</p>
    {% endfor %}
    """, resources=resources)


@app.route('/allocate', methods=['GET', 'POST'])
def allocate():
    events = Event.query.all()
    resources = Resource.query.all()

    if not events or not resources:
        flash("Please create events and resources before allocation")

    if request.method == 'POST':
        event = Event.query.get(int(request.form['event']))
        resource_id = int(request.form['resource'])

        if has_conflict(resource_id, event.start_time, event.end_time):
            flash("Resource conflict detected")
        else:
            db.session.add(Allocation(
                event_id=event.id,
                resource_id=resource_id
            ))
            db.session.commit()
            flash("Resource allocated successfully")

    return render_template_string("""
    <h3>Allocate Resource</h3>
    {% for m in get_flashed_messages() %}
        <p>{{m}}</p>
    {% endfor %}

    <form method="post">
        Event:
        <select name="event">
            {% for e in events %}
                <option value="{{e.id}}">{{e.title}}</option>
            {% endfor %}
        </select>

        Resource:
        <select name="resource">
            {% for r in resources %}
                <option value="{{r.id}}">{{r.name}}</option>
            {% endfor %}
        </select>
        <button>Allocate</button>
    </form>
    """, events=events, resources=resources)


@app.route('/report', methods=['GET', 'POST'])
def report():
    data = []

    if request.method == 'POST':
        start = parse_datetime(request.form['start'])
        end = parse_datetime(request.form['end'])

        for r in Resource.query.all():
            total_hours = 0
            upcoming = 0

            for a in Allocation.query.filter_by(resource_id=r.id):
                e = a.event

                # Overlap calculation
                if start < e.end_time and e.start_time < end:
                    overlap_start = max(start, e.start_time)
                    overlap_end = min(end, e.end_time)
                    total_hours += (overlap_end - overlap_start).total_seconds() / 3600

                if e.start_time > datetime.now():
                    upcoming += 1

            data.append((r.name, round(total_hours, 2), upcoming))

    return render_template_string("""
    <h3>Resource Utilisation Report</h3>
    <form method="post">
        From: <input type="datetime-local" name="start" required>
        To: <input type="datetime-local" name="end" required>
        <button>Generate</button>
    </form>

    <table border="1" cellpadding="5">
        <tr>
            <th>Resource</th>
            <th>Total Hours</th>
            <th>Upcoming Bookings</th>
        </tr>
        {% for d in data %}
            <tr>
                <td>{{d[0]}}</td>
                <td>{{d[1]}}</td>
                <td>{{d[2]}}</td>
            </tr>
        {% endfor %}
    </table>
    """, data=data)


# ---------------- APP START ----------------

if __name__ == '__main__':
    with app.app_context():
        db.drop_all()    
        db.create_all() 
    app.run(debug=True)
