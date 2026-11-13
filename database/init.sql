CREATE DATABASE IF NOT EXISTS jobsphere;
USE jobsphere;

-- ==============================
-- USERS TABLE
-- ==============================
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(180) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('candidate', 'recruiter') NOT NULL DEFAULT 'candidate',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==============================
-- JOBS TABLE
-- ==============================
CREATE TABLE IF NOT EXISTS jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    company VARCHAR(150) NOT NULL,
    location VARCHAR(120) NOT NULL DEFAULT 'Remote',
    type ENUM('Full-Time', 'Part-Time', 'Internship', 'Contract', 'Remote') NOT NULL DEFAULT 'Full-Time',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_jobs_type (type),
    INDEX idx_jobs_company (company)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==============================
-- APPLICATIONS TABLE
-- ==============================
CREATE TABLE IF NOT EXISTS applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id INT NOT NULL,
    candidate_id INT NOT NULL,
    status ENUM(
        'Applied',
        'Under Review',
        'Shortlisted',
        'Interview Scheduled',
        'Rejected',
        'Hired'
    ) NOT NULL DEFAULT 'Applied',
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_job_candidate (job_id, candidate_id),
    CONSTRAINT fk_applications_job
        FOREIGN KEY (job_id) REFERENCES jobs(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_applications_candidate
        FOREIGN KEY (candidate_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==============================
-- SEED DATA (INITIAL JOBS)
-- ==============================
INSERT INTO jobs (title, company, location, type) VALUES
    ('Cloud & DevOps Engineer', 'Stratosphere Systems', 'Bengaluru, India', 'Full-Time'),
    ('Backend Python Developer', 'NexaTech Solutions', 'Remote', 'Full-Time'),
    ('Kubernetes Platform Intern', 'KubeScale Labs', 'Kochi, India', 'Internship'),
    ('Full Stack Software Engineer', 'Aether Digital', 'Hyderabad, India', 'Contract');