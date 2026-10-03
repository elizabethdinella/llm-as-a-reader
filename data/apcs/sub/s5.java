public Account(String requestedName) {

    if (isAvailable(requestedName)) {
        username = requestedName;
        return;
    }

    int itr = 1;

    while (!isAvailable(requestedName + itr)) {
        itr++;
    }

    username = requestedName + itr;
}

public String getShortenedName() {
    return username.replace("-", "");
}
