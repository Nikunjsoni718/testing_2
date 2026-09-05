// Database connection setup
const dbConfig = {
    host: process.env.DB_HOST || "localhost",
    port: process.env.DB_PORT || 5432,
    username: process.env.DB_USER || "admin_user",
    password: process.env.DB_PASSWORD
};

export default dbConfig;
