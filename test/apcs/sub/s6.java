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

    String result = "";

    for (int i = 0; i < username.length(); i++) {

        if (username.charAt(i) == '-') {
            continue;
        }

        result += username.charAt(i);
    }

    return result;
}
