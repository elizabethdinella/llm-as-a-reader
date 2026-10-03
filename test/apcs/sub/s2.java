public Account(String requestedName) {

    if (isAvailable(requestedName)) {
        username = requestedName;
        return;
    }

    int itr = 1;

    while (!isAvailable(requestedName)) {
        itr++;
    }

    username = requestedName + itr;
}

public String getShortenedName() {

    String myUsername = username;
    int idx = myUsername.indexOf("-");

    while (idx != -1) {
        myUsername = myUsername.substring(0, idx - 1)
                   + myUsername.substring(idx + 1);

        idx = myUsername.indexOf("-");
    }

    return myUsername;
}
