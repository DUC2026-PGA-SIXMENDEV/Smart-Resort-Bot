CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    language TEXT,
    is_blocked INTEGER DEFAULT 0,
    created_at DATETIME,
    last_seen DATETIME
);

CREATE TABLE bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    guest_name TEXT NOT NULL,
    checkin DATE NOT NULL,
    checkout DATE NOT NULL,
    room_type TEXT NOT NULL,
    num_guests INTEGER,
    special_request TEXT,
    status TEXT DEFAULT 'PENDING',

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
);

CREATE TABLE admin_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,

    FOREIGN KEY (booking_id)
        REFERENCES bookings(id)
);