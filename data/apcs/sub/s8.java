public Account(String requestedName)
{
    if (isAvailable(requestedName))
    {
        username = requestedName;
    }
    else
    {
        int count = 1;

        while (!isAvailable(requestedName + count))
        {
            count++;
        }
        username = requestedName + count;
    }
}

public String getShortenedName()
{
    String result = username;

    while (result.indexOf("-") >= 0)
    {
        int j = result.indexOf("-");
        result = result.substring(0, j - 1) +
                 result.substring(j + 1);
    }

    return result;
}
