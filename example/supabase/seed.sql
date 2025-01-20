-- Create a table for holding todos
CREATE TABLE todos(
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    description text,
    is_completed boolean DEFAULT FALSE,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

ALTER publication supabase_realtime
    ADD TABLE todos;
