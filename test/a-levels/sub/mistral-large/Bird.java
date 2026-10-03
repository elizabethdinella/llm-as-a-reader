public class Bird {
    // Private attributes
    private double distancePerHour;
    private String species;
    private double xPosition = 500.0;
    private double yPosition = 500.0;

    // Constructor
    public Bird(String species, double distancePerHour) {
        this.species = species;
        this.distancePerHour = distancePerHour;
    }

    public static void main(String[] args) {
        Bird b = new Bird("canary", 100);
        System.out.println(b);
    }
}
