public Account(String requestedName)
{
    if (Account.isAvailable())
    {
        username = requestedName;
    }
    else
    {
        int count = 1;

        while (!Account.isAvailable())
        {
        }

        username = requestedName;
    }
}
