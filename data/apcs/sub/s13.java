public Account(String requestedName)
{
    if (isAvailable(requestedName))
    {
        username = requestedName;
    }
    else
    {
        int count = 1;

        while (!isAvailable(requestedName))
        {
        }

        username = requestedName + count;
    }
}
