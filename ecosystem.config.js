module.exports = {
  apps: [
    {
      name: "mafia-bot",
      script: "main.py",
      cwd: "./mafia_bot",
      interpreter: "python3",
      watch: false,
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      env: {
        PYTHONPATH: "./mafia_bot",
        PYTHONUNBUFFERED: "1",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "./logs/bot-error.log",
      out_file: "./logs/bot-out.log",
      merge_logs: true,
    },
  ],
};
