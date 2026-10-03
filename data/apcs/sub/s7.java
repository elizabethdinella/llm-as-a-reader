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

    String myUsername = username;

    while (myUsername.indexOf("-") != -1) {

        int idx = myUsername.indexOf("-");

        myUsername = myUsername.substring(0, idx)
                   + myUsername.substring(idx + 1);
    }

    return myUsername;
}
