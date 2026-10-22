import { Component, EventEmitter, Output } from "@angular/core";
import { CommonModule } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { AuthService } from "./auth.service";

@Component({
  selector: "app-login",
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <h1>PLC Dashboard Login</h1>
    <form (ngSubmit)="submit()">
      <input [(ngModel)]="username" name="username" placeholder="Username" required />
      <input [(ngModel)]="password" name="password" type="password" placeholder="Password" required />
      <button type="submit">Log in</button>
    </form>
    <p *ngIf="error">{{ error }}</p>
  `,
})
export class LoginComponent {
  @Output() loggedIn = new EventEmitter<void>();
  username = "";
  password = "";
  error = "";

  constructor(private auth: AuthService) {}

  async submit() {
    this.error = "";
    try {
      await this.auth.login(this.username, this.password);
      this.loggedIn.emit();
    } catch {
      this.error = "Invalid credentials";
    }
  }
}
