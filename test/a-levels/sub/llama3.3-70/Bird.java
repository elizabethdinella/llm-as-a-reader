public class Bird {
    private double distancePerHour;
    private String species;
    private double xPosition;
    private double yPosition;

    public Bird(double distancePerHour, String species) {
        this.distancePerHour = distancePerHour;
        this.species = species;
        this.xPosition = 500.0;
        this.yPosition = 500.0;
    }

    public String getPosition() {
        return "X = " + xPosition + " Y = " + yPosition;
    }

    public static void main(String[] args) {
        Bird b = new Bird(100, "canary");
        System.out.println(b.getPosition());
    }
}

