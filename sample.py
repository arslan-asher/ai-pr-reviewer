# sample.py
def get_user_by_id(user_id: int):
    user = db.query(user_id)
    if not user:
        # Status code 400 will be flagged by AI (should be 404 for not found)
        raise Exception("User not found", 400)
    return user
